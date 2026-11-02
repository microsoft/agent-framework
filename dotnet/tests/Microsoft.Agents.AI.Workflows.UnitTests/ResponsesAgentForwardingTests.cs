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
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using OpenAI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// End-to-end tests for replies that workflows forward between agents backed by the OpenAI Responses API. They
/// run real <see cref="ChatClientAgent"/>s over the real MEAI OpenAI Responses client and a fake HTTP transport
/// that rejects input the service rejects, so the request body each agent sends is checked.
/// </summary>
public class ResponsesAgentForwardingTests
{
    private const string Draft = "Draft from AgentA.";
    private const string Review = "Review from AgentB.";

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Magentic_ForwardedReply_IsSentAsInputText_AndAuthorKeepsOutputTextAsync(bool emitEvents)
    {
        // Arrange: the manager hands the task to AgentA, then AgentB, then AgentA again, then finishes.
        using FakeResponsesModel managerModel = new(
            "Facts: none needed.",
            "Plan: AgentA drafts, AgentB reviews, AgentA revises.",
            CreateProgressLedger(isRequestSatisfied: false, nextSpeaker: "AgentA", instruction: "Write the draft."),
            CreateProgressLedger(isRequestSatisfied: false, nextSpeaker: "AgentB", instruction: "Review the draft."),
            CreateProgressLedger(isRequestSatisfied: false, nextSpeaker: "AgentA", instruction: "Apply the review."),
            CreateProgressLedger(isRequestSatisfied: true, nextSpeaker: "AgentA", instruction: "Done."),
            "Final answer.");
        using FakeResponsesModel modelA = new(Draft, "Revision from AgentA.");
        using FakeResponsesModel modelB = new(Review);

        Workflow workflow = new MagenticWorkflowBuilder(CreateAgent(managerModel, "Manager"))
            .AddParticipants(CreateAgent(modelA, "AgentA"), CreateAgent(modelB, "AgentB"))
            .RequirePlanSignoff(false)
            .Build();

        // Act: without update events the participants run non-streaming.
        (List<ChatMessage>? output, List<string> errors) = await RunAsync(workflow, emitEvents);

        // Assert: the workflow finished and the service accepted every request.
        Assert.True(errors.Count == 0, string.Join(Environment.NewLine, errors));
        Assert.Empty(managerModel.Rejections.Concat(modelA.Rejections).Concat(modelB.Rejections));
        Assert.NotNull(output);
        Assert.Contains("Final answer.", output![0].Text);

        // The participants ran in the requested mode.
        AssertStreamed(emitEvents, modelA, modelB);

        // AgentB received AgentA's reply as user input text.
        AssertInputMessage(Assert.Single(modelB.Requests), Draft, "user", "input_text");

        // AgentA's second request replays its own reply unchanged and AgentB's reply as user input text.
        Assert.Equal(2, modelA.Requests.Count);
        AssertInputMessage(modelA.Requests[1], Draft, "assistant", "output_text");
        AssertInputMessage(modelA.Requests[1], Review, "user", "input_text");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Sequential_ForwardedReply_IsSentAsInputTextAsync(bool emitEvents)
    {
        // Arrange
        using FakeResponsesModel modelA = new(Draft);
        using FakeResponsesModel modelB = new(Review);
        Workflow workflow = AgentWorkflowBuilder.BuildSequential(CreateAgent(modelA, "AgentA"), CreateAgent(modelB, "AgentB"));

        // Act
        (_, List<string> errors) = await RunAsync(workflow, emitEvents);

        // Assert: the agents ran in the requested mode and AgentB received AgentA's reply as user input text.
        Assert.True(errors.Count == 0, string.Join(Environment.NewLine, errors));
        AssertStreamed(emitEvents, modelA, modelB);
        AssertInputMessage(Assert.Single(modelB.Requests), Draft, "user", "input_text");
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task GroupChat_ForwardedReply_IsSentAsInputTextAsync(bool emitEvents)
    {
        // Arrange: round robin lets AgentA speak, then AgentB.
        using FakeResponsesModel modelA = new(Draft);
        using FakeResponsesModel modelB = new(Review);
        Workflow workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(CreateAgent(modelA, "AgentA"), CreateAgent(modelB, "AgentB"))
            .Build();

        // Act
        (_, List<string> errors) = await RunAsync(workflow, emitEvents);

        // Assert: the agents ran in the requested mode and AgentB received AgentA's reply as user input text.
        Assert.True(errors.Count == 0, string.Join(Environment.NewLine, errors));
        AssertStreamed(emitEvents, modelA, modelB);
        AssertInputMessage(Assert.Single(modelB.Requests), Draft, "user", "input_text");
    }

    private static ChatClientAgent CreateAgent(FakeResponsesModel model, string name)
    {
        IChatClient chatClient = new OpenAIClient(
                new ApiKeyCredential("test-key"),
                new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(model.HttpClient) })
            .GetResponsesClient()
            .AsIChatClient("test-model");

        return new ChatClientAgent(chatClient, name: name, description: $"The {name} participant.");
    }

    private static async Task<(List<ChatMessage>? Output, List<string> Errors)> RunAsync(Workflow workflow, bool emitEvents)
    {
        List<ChatMessage>? output = null;
        List<string> errors = [];
        using CancellationTokenSource timeout = new(TimeSpan.FromSeconds(30));

        await using StreamingRun run = await InProcessExecution.OpenStreamingAsync(workflow);
        await run.TrySendMessageAsync(new List<ChatMessage> { new(ChatRole.User, "Write a draft, review it, then revise it.") });
        await run.TrySendMessageAsync(new TurnToken(emitEvents));

        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false, timeout.Token))
        {
            switch (evt)
            {
                case ExecutorFailedEvent failed:
                    errors.Add($"{failed.ExecutorId}: {failed.Data?.Message}");
                    break;

                case WorkflowErrorEvent error:
                    errors.Add($"workflow: {error.Exception?.Message}");
                    break;

                case WorkflowOutputEvent outputEvent when outputEvent.Is<List<ChatMessage>>():
                    output = outputEvent.As<List<ChatMessage>>();
                    break;
            }
        }

        return (output, errors);
    }

    private static void AssertStreamed(bool expected, params FakeResponsesModel[] models) =>
        Assert.All(models.SelectMany(model => model.Requests), request =>
            Assert.Equal(expected, request.TryGetProperty("stream", out JsonElement stream) && stream.GetBoolean()));

    private static void AssertInputMessage(JsonElement request, string text, string role, string partType)
    {
        JsonElement message = request.GetProperty("input").EnumerateArray().Single(item =>
            item.TryGetProperty("content", out JsonElement content)
            && content.ValueKind == JsonValueKind.Array
            && content.EnumerateArray().Any(part => string.Equals(part.GetProperty("text").GetString(), text, StringComparison.Ordinal)));

        Assert.Equal(role, message.GetProperty("role").GetString());
        JsonElement part = Assert.Single(message.GetProperty("content").EnumerateArray());
        Assert.Equal(partType, part.GetProperty("type").GetString());
    }

    private static string CreateProgressLedger(bool isRequestSatisfied, string nextSpeaker, string instruction) =>
        new JsonObject
        {
            ["is_request_satisfied"] = new JsonObject { ["answer"] = isRequestSatisfied, ["reason"] = "test reason" },
            ["is_in_loop"] = new JsonObject { ["answer"] = false, ["reason"] = "test reason" },
            ["is_progress_being_made"] = new JsonObject { ["answer"] = true, ["reason"] = "test reason" },
            ["next_speaker"] = new JsonObject { ["answer"] = nextSpeaker, ["reason"] = "test reason" },
            ["instruction_or_question"] = new JsonObject { ["answer"] = instruction, ["reason"] = "test reason" },
        }.ToJsonString();

    /// <summary>
    /// Serves one canned assistant reply per request, as JSON or as an event stream to match the request, records each
    /// request body, and answers with the service's 400 error when a message content part is not valid for its role.
    /// </summary>
    private sealed class FakeResponsesModel : HttpMessageHandler
    {
        private static readonly string[] s_inputPartTypes = ["input_text", "input_image", "input_file", "scoped_content", "input_audio"];
        private const string InputPartTypesText = "'input_text', 'input_image', 'input_file', 'scoped_content', and 'input_audio'";
        private static readonly string[] s_outputPartTypes = ["output_text", "refusal"];
        private const string OutputPartTypesText = "'output_text' and 'refusal'";

        private readonly Queue<string> _replies;

        public FakeResponsesModel(params string[] replies)
        {
            this._replies = new Queue<string>(replies);
#pragma warning disable CA5399 // Fake transport, no certificate revocation involved.
            this.HttpClient = new HttpClient(this, disposeHandler: false);
#pragma warning restore CA5399
        }

        public HttpClient HttpClient { get; }

        public List<JsonElement> Requests { get; } = [];

        public List<string> Rejections { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
#if NET
            string body = await request.Content!.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#else
            string body = await request.Content!.ReadAsStringAsync().ConfigureAwait(false);
#endif
            using JsonDocument document = JsonDocument.Parse(body);
            JsonElement requestJson = document.RootElement.Clone();
            this.Requests.Add(requestJson);

            if (FindInvalidContentPart(requestJson) is { } error)
            {
                this.Rejections.Add(error);
                return new HttpResponseMessage(HttpStatusCode.BadRequest)
                {
                    Content = new StringContent(error, Encoding.UTF8, "application/json"),
                    RequestMessage = request,
                };
            }

            string text = this._replies.Dequeue();
            string responseId = $"resp_{Guid.NewGuid():N}";
            string messageId = $"msg_{Guid.NewGuid():N}";
            bool stream = requestJson.TryGetProperty("stream", out JsonElement streamJson) && streamJson.ValueKind == JsonValueKind.True;
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = stream
                    ? new StringContent(CreateEventStream(responseId, messageId, text), Encoding.UTF8, "text/event-stream")
                    : new StringContent(CreateResponse(responseId, "completed", CreateMessage(messageId, "completed", text)).ToJsonString(), Encoding.UTF8, "application/json"),
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

        private static string? FindInvalidContentPart(JsonElement requestJson)
        {
            if (!requestJson.TryGetProperty("input", out JsonElement input) || input.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            int itemIndex = 0;
            foreach (JsonElement item in input.EnumerateArray())
            {
                if (item.TryGetProperty("role", out JsonElement role)
                    && item.TryGetProperty("content", out JsonElement content)
                    && content.ValueKind == JsonValueKind.Array)
                {
                    bool isAssistant = string.Equals(role.GetString(), "assistant", StringComparison.Ordinal);
                    string[] allowed = isAssistant ? s_outputPartTypes : s_inputPartTypes;
                    int partIndex = 0;
                    foreach (JsonElement part in content.EnumerateArray())
                    {
                        string? type = part.GetProperty("type").GetString();
                        if (!allowed.Contains(type, StringComparer.Ordinal))
                        {
                            return new JsonObject
                            {
                                ["error"] = new JsonObject
                                {
                                    ["message"] = $"Invalid value: '{type}'. Supported values are: {(isAssistant ? OutputPartTypesText : InputPartTypesText)}.",
                                    ["type"] = "invalid_request_error",
                                    ["param"] = $"input[{itemIndex}].content[{partIndex}]",
                                    ["code"] = "invalid_value",
                                },
                            }.ToJsonString();
                        }

                        partIndex++;
                    }
                }

                itemIndex++;
            }

            return null;
        }

        private static string CreateEventStream(string responseId, string messageId, string text)
        {
            JsonObject message = CreateMessage(messageId, "completed", text);
            (string Type, JsonObject Data)[] events =
            [
                ("response.created", new() { ["response"] = CreateResponse(responseId, "in_progress", message: null) }),
                ("response.output_item.added", new() { ["output_index"] = 0, ["item"] = CreateMessage(messageId, "in_progress", text: null) }),
                ("response.content_part.added", new() { ["item_id"] = messageId, ["output_index"] = 0, ["content_index"] = 0, ["part"] = CreateOutputTextPart(string.Empty) }),
                ("response.output_text.delta", new() { ["item_id"] = messageId, ["output_index"] = 0, ["content_index"] = 0, ["delta"] = text, ["logprobs"] = new JsonArray() }),
                ("response.output_text.done", new() { ["item_id"] = messageId, ["output_index"] = 0, ["content_index"] = 0, ["text"] = text, ["logprobs"] = new JsonArray() }),
                ("response.content_part.done", new() { ["item_id"] = messageId, ["output_index"] = 0, ["content_index"] = 0, ["part"] = CreateOutputTextPart(text) }),
                ("response.output_item.done", new() { ["output_index"] = 0, ["item"] = message.DeepClone() }),
                ("response.completed", new() { ["response"] = CreateResponse(responseId, "completed", message) }),
            ];

            StringBuilder builder = new();
            for (int i = 0; i < events.Length; i++)
            {
                JsonObject data = new() { ["type"] = events[i].Type, ["sequence_number"] = i };
                foreach (KeyValuePair<string, JsonNode?> property in events[i].Data)
                {
                    data[property.Key] = property.Value?.DeepClone();
                }

                builder.Append("event: ").Append(events[i].Type).Append('\n');
                builder.Append("data: ").Append(data.ToJsonString()).Append("\n\n");
            }

            return builder.ToString();
        }

        private static JsonObject CreateResponse(string responseId, string status, JsonObject? message) => new()
        {
            ["id"] = responseId,
            ["object"] = "response",
            ["created_at"] = 1762941294,
            ["status"] = status,
            ["model"] = "test-model",
            ["output"] = message is null ? new JsonArray() : new JsonArray(message.DeepClone()),
            ["parallel_tool_calls"] = true,
            ["tool_choice"] = "auto",
            ["tools"] = new JsonArray(),
            // Without stored output each agent keeps its own history and resends all of it on every request.
            ["store"] = false,
            ["text"] = new JsonObject { ["format"] = new JsonObject { ["type"] = "text" } },
            ["truncation"] = "disabled",
        };

        private static JsonObject CreateMessage(string messageId, string status, string? text) => new()
        {
            ["type"] = "message",
            ["id"] = messageId,
            ["status"] = status,
            ["role"] = "assistant",
            ["content"] = text is null ? new JsonArray() : new JsonArray(CreateOutputTextPart(text)),
        };

        private static JsonObject CreateOutputTextPart(string text) => new()
        {
            ["type"] = "output_text",
            ["text"] = text,
            ["annotations"] = new JsonArray(),
        };
    }
}
