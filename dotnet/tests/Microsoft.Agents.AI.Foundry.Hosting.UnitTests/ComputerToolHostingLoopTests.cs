// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using OpenAIClient = OpenAI.OpenAIClient;
using OpenAIClientOptions = OpenAI.OpenAIClientOptions;

#pragma warning disable OPENAI001 // Experimental Responses API surfaces
#pragma warning disable OPENAICUA001 // FoundryAITool.CreateComputerTool is experimental.

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// End-to-end tests for the hosted GA computer tool loop. They run the real hosting handler, a real
/// <see cref="ChatClientAgent"/> and the real MEAI OpenAI Responses client over a fake HTTP transport, so both
/// the items the caller receives and the exact request body sent to the model are checked.
/// </summary>
public sealed class ComputerToolHostingLoopTests
{
    private const string ModelCallId = "call_ga_1";
    private const string ModelItemId = "cu_model_item_1";
    private const string ScreenshotUrl = "data:image/png;base64,iVBORw0KGgo=";

    // Shape the service returns for the GA tool: an ordered actions batch, and neither "action" nor "pending_safety_checks".
    private const string BatchedComputerCallJson =
        "{\"type\":\"computer_call\",\"id\":\"" + ModelItemId + "\",\"call_id\":\"" + ModelCallId + "\"," +
        "\"actions\":[{\"type\":\"click\",\"button\":\"left\",\"x\":405,\"y\":157},{\"type\":\"type\",\"text\":\"penguin\"}]," +
        "\"status\":\"completed\"}";

    [Fact]
    public async Task CreateAsync_ModelReturnsBatchedComputerCall_EmitsComputerCallWithActionsAsync()
    {
        // Arrange
        using var model = new FakeResponsesModel(ComputerCallTurn());
        var handler = BuildHandler(model);
        var request = NewRequest(UserMessageInput("Search for penguin."));

        // Act
        var events = await DrainAsync(handler.CreateAsync(request, NewContext("resp_" + new string('1', 46), request, []), CancellationToken.None));

        // Assert: the caller receives the model's computer call, with the batch intact.
        var added = Assert.Single(events.OfType<ResponseOutputItemAddedEvent>().Select(e => e.Item).OfType<OutputItemComputerToolCall>());
        var done = Assert.Single(events.OfType<ResponseOutputItemDoneEvent>().Select(e => e.Item).OfType<OutputItemComputerToolCall>());
        Assert.Equal(added.Id, done.Id);
        Assert.StartsWith("cu_", done.Id, StringComparison.Ordinal);
        Assert.NotEqual(ModelItemId, done.Id);
        Assert.Equal(ModelCallId, done.CallId);
        Assert.Equal(2, done.Actions.Count);

        string doneJson = ModelReaderWriter.Write(done, ModelReaderWriterOptions.Json).ToString();
        Assert.Contains("\"actions\":[{\"type\":\"click\"", doneJson);
        Assert.DoesNotContain("\"action\":", doneJson);
        Assert.IsType<ResponseCompletedEvent>(events[^1]);

        // Assert: the model was offered the GA tool, and nothing was stored on the model service.
        using var sent = JsonDocument.Parse(Assert.Single(model.RequestBodies));
        Assert.Equal("{\"type\":\"computer\"}", Assert.Single(sent.RootElement.GetProperty("tools").EnumerateArray()).GetRawText());
        Assert.False(sent.RootElement.GetProperty("store").GetBoolean());
    }

    [Fact]
    public async Task CreateAsync_ComputerCallOutputAfterStoredComputerCall_ReplaysBothItemsToModelAsync()
    {
        // Arrange: history as AgentServer returns it, including the envelope fields it adds to output items.
        const string HistoryItemId = "cu_" + "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
        var storedCall = ReadOutputItem(
            "{\"type\":\"computer_call\",\"id\":\"" + HistoryItemId + "\",\"call_id\":\"" + ModelCallId + "\"," +
            "\"actions\":[{\"type\":\"click\",\"button\":\"left\",\"x\":405,\"y\":157},{\"type\":\"type\",\"text\":\"penguin\"}]," +
            "\"pending_safety_checks\":[],\"status\":\"completed\"," +
            "\"response_id\":\"resp_previous\",\"agent_reference\":{\"type\":\"agent_reference\",\"name\":\"computer-agent\"}}");
        IReadOnlyList<OutputItem> history = [UserHistoryMessage("Search for penguin."), storedCall];

        using var model = new FakeResponsesModel(TextTurn("Done."));
        var handler = BuildHandler(model);
        var request = NewRequest(ComputerCallOutputInput(ModelCallId));

        // Act
        await DrainAsync(handler.CreateAsync(request, NewContext("resp_" + new string('2', 46), request, history), CancellationToken.None));

        // Assert
        using var sent = JsonDocument.Parse(Assert.Single(model.RequestBodies));
        var input = sent.RootElement.GetProperty("input").EnumerateArray().ToList();
        int callIndex = input.FindIndex(i => i.GetProperty("type").GetString() == "computer_call");
        int outputIndex = input.FindIndex(i => i.GetProperty("type").GetString() == "computer_call_output");
        Assert.True(callIndex >= 0, "The stored computer_call was not replayed to the model.");
        Assert.True(outputIndex > callIndex, "The computer_call_output must follow its computer_call.");

        AssertReplayedComputerCall(input[callIndex], HistoryItemId);
        AssertReplayedComputerCallOutput(input[outputIndex]);
    }

    [Fact]
    public async Task CreateAsync_TwoTurnComputerLoop_ReplaysEmittedCallWithCallerOutputAsync()
    {
        // Arrange: turn 1 returns a computer call, turn 2 answers with text.
        using var model = new FakeResponsesModel(ComputerCallTurn(), TextTurn("Done."));
        var handler = BuildHandler(model);

        var firstRequest = NewRequest(UserMessageInput("Search for penguin."));
        var firstEvents = await DrainAsync(handler.CreateAsync(firstRequest, NewContext("resp_" + new string('3', 46), firstRequest, []), CancellationToken.None));
        var emittedCall = Assert.Single(firstEvents.OfType<ResponseOutputItemDoneEvent>().Select(e => e.Item).OfType<OutputItemComputerToolCall>());

        // The caller runs the actions and returns a screenshot; AgentServer supplies turn 1 as history.
        IReadOnlyList<OutputItem> history = [UserHistoryMessage("Search for penguin."), emittedCall];
        var secondRequest = NewRequest(ComputerCallOutputInput(emittedCall.CallId));

        // Act
        await DrainAsync(handler.CreateAsync(secondRequest, NewContext("resp_" + new string('4', 46), secondRequest, history), CancellationToken.None));

        // Assert: the second model request carries the call the caller saw, then the caller's output.
        Assert.Equal(2, model.RequestBodies.Count);
        using var sent = JsonDocument.Parse(model.RequestBodies[1]);
        var input = sent.RootElement.GetProperty("input").EnumerateArray().ToList();
        int callIndex = input.FindIndex(i => i.GetProperty("type").GetString() == "computer_call");
        int outputIndex = input.FindIndex(i => i.GetProperty("type").GetString() == "computer_call_output");
        Assert.True(callIndex >= 0, "The emitted computer_call was not replayed to the model.");
        Assert.True(outputIndex > callIndex, "The computer_call_output must follow its computer_call.");

        AssertReplayedComputerCall(input[callIndex], emittedCall.Id);
        AssertReplayedComputerCallOutput(input[outputIndex]);
    }

    private static void AssertReplayedComputerCall(JsonElement call, string expectedId)
    {
        Assert.Equal(expectedId, call.GetProperty("id").GetString());
        Assert.Equal(ModelCallId, call.GetProperty("call_id").GetString());

        var actions = call.GetProperty("actions").EnumerateArray().ToList();
        Assert.Equal(2, actions.Count);
        Assert.Equal("click", actions[0].GetProperty("type").GetString());
        Assert.Equal("penguin", actions[1].GetProperty("text").GetString());

        // AgentServer envelope fields are not part of the model's item schema and must not reach the model.
        Assert.False(call.TryGetProperty("response_id", out _));
        Assert.False(call.TryGetProperty("agent_reference", out _));

        // OpenAI .NET 2.13.0 re-serializes the GA call with "action": null and "pending_safety_checks": [], and the
        // service rejects both on replay (see the known-issue test in InputConverterTests). These tests check what MAF
        // controls: a populated single action here would mean the batch was rewritten.
        if (call.TryGetProperty("action", out JsonElement action))
        {
            Assert.Equal(JsonValueKind.Null, action.ValueKind);
        }
    }

    private static void AssertReplayedComputerCallOutput(JsonElement output)
    {
        Assert.Equal(ModelCallId, output.GetProperty("call_id").GetString());
        JsonElement screenshot = output.GetProperty("output");
        Assert.Equal("computer_screenshot", screenshot.GetProperty("type").GetString());
        Assert.Equal(ScreenshotUrl, screenshot.GetProperty("image_url").GetString());
        Assert.Equal("original", screenshot.GetProperty("detail").GetString());
        Assert.False(output.TryGetProperty("response_id", out _));
        Assert.False(output.TryGetProperty("agent_reference", out _));
    }

    private static AgentFrameworkResponseHandler BuildHandler(FakeResponsesModel model)
    {
        IChatClient chatClient = new OpenAIClient(
                new ApiKeyCredential("test-key"),
                new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(model.HttpClient) })
            .GetResponsesClient()
            .AsIChatClient("test-model");

        var agent = new ChatClientAgent(chatClient, new ChatClientAgentOptions
        {
            ChatOptions = new ChatOptions { Tools = [FoundryAITool.CreateComputerTool()] },
        });

        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new InMemoryAgentSessionStore());
        services.AddSingleton<AIAgent>(agent);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        return new AgentFrameworkResponseHandler(services.BuildServiceProvider(), NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    private static CreateResponse NewRequest(object[] input) =>
        new() { Model = "test", Input = BinaryData.FromObjectAsJson(input) };

    private static object[] UserMessageInput(string text) =>
    [
        new
        {
            type = "message",
            id = "msg_1",
            status = "completed",
            role = "user",
            content = new[] { new { type = "input_text", text } },
        },
    ];

    private static object[] ComputerCallOutputInput(string callId) =>
    [
        new
        {
            type = "computer_call_output",
            call_id = callId,
            output = new { type = "computer_screenshot", image_url = ScreenshotUrl, detail = "original" },
        },
    ];

    private static ResponseContext NewContext(string responseId, CreateResponse request, IReadOnlyList<OutputItem> history)
    {
        IReadOnlyList<Item> inputItems = request.GetInputExpanded().ToList();
        var context = new Mock<ResponseContext>(responseId) { CallBase = true };
        context.Setup(x => x.PlatformContext).Returns(new PlatformContext("alice", null));
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>())).ReturnsAsync(history);
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>())).ReturnsAsync(inputItems);
        return context.Object;
    }

    private static OutputItemMessage UserHistoryMessage(string text) =>
        new(
            id: "msg_history_1",
            role: MessageRole.User,
            content: new MessageContent[] { new MessageContentInputTextContent(text) },
            status: MessageStatus.Completed);

    private static OutputItem ReadOutputItem(string json) =>
        ModelReaderWriter.Read<OutputItem>(BinaryData.FromString(json), ModelReaderWriterOptions.Json, AzureAIAgentServerResponsesContext.Default)!;

    private static async Task<List<ResponseStreamEvent>> DrainAsync(IAsyncEnumerable<ResponseStreamEvent> events)
    {
        var list = new List<ResponseStreamEvent>();
        await foreach (var evt in events)
        {
            list.Add(evt);
        }

        return list;
    }

    private static string ComputerCallTurn()
    {
        string inProgressCall = BatchedComputerCallJson.Replace("\"status\":\"completed\"", "\"status\":\"in_progress\"");
        return Sse(
            ("response.created", "{\"type\":\"response.created\",\"sequence_number\":0,\"response\":" + ResponseJson("in_progress", string.Empty) + "}"),
            ("response.output_item.added", "{\"type\":\"response.output_item.added\",\"sequence_number\":1,\"output_index\":0,\"item\":" + inProgressCall + "}"),
            ("response.output_item.done", "{\"type\":\"response.output_item.done\",\"sequence_number\":2,\"output_index\":0,\"item\":" + BatchedComputerCallJson + "}"),
            ("response.completed", "{\"type\":\"response.completed\",\"sequence_number\":3,\"response\":" + ResponseJson("completed", BatchedComputerCallJson) + "}"));
    }

    private static string TextTurn(string text)
    {
        string message = "{\"type\":\"message\",\"id\":\"msg_model_2\",\"status\":\"completed\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"" + text + "\",\"annotations\":[]}]}";
        return Sse(
            ("response.created", "{\"type\":\"response.created\",\"sequence_number\":0,\"response\":" + ResponseJson("in_progress", string.Empty) + "}"),
            ("response.output_text.delta", "{\"type\":\"response.output_text.delta\",\"sequence_number\":1,\"item_id\":\"msg_model_2\",\"output_index\":0,\"content_index\":0,\"delta\":\"" + text + "\"}"),
            ("response.output_item.done", "{\"type\":\"response.output_item.done\",\"sequence_number\":2,\"output_index\":0,\"item\":" + message + "}"),
            ("response.completed", "{\"type\":\"response.completed\",\"sequence_number\":3,\"response\":" + ResponseJson("completed", message) + "}"));
    }

    private static string ResponseJson(string status, string outputItemJson) =>
        "{\"id\":\"resp_model_1\",\"object\":\"response\",\"created_at\":1762941294,\"status\":\"" + status + "\"," +
        "\"model\":\"test-model\",\"output\":[" + outputItemJson + "],\"parallel_tool_calls\":true,\"tool_choice\":\"auto\"," +
        "\"tools\":[{\"type\":\"computer\"}],\"store\":false,\"text\":{\"format\":{\"type\":\"text\"}},\"truncation\":\"disabled\"}";

    private static string Sse(params (string EventType, string Data)[] events)
    {
        var builder = new StringBuilder();
        foreach (var (eventType, data) in events)
        {
            builder.Append("event: ").Append(eventType).Append('\n');
            builder.Append("data: ").Append(data).Append("\n\n");
        }

        return builder.ToString();
    }

    /// <summary>Serves one canned server-sent-event stream per model request and records each request body.</summary>
    private sealed class FakeResponsesModel : HttpMessageHandler
    {
        private readonly Queue<string> _turns;

        public FakeResponsesModel(params string[] turns)
        {
            this._turns = new Queue<string>(turns);
#pragma warning disable CA5399 // Fake transport, no certificate revocation involved.
            this.HttpClient = new HttpClient(this, disposeHandler: false);
#pragma warning restore CA5399
        }

        public HttpClient HttpClient { get; }

        public List<string> RequestBodies { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.RequestBodies.Add(await request.Content!.ReadAsStringAsync(cancellationToken).ConfigureAwait(false));
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._turns.Dequeue(), Encoding.UTF8, "text/event-stream"),
                RequestMessage = request,
            };
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this.HttpClient.Dispose();
            }

            base.Dispose(disposing);
        }
    }
}
