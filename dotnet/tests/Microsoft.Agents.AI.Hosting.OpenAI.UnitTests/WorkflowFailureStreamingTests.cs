// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Agents.AI.Workflows;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Verifies that workflow failures reported through the Responses API use the error text selected by
/// the workflow host, as controlled by its <c>includeExceptionDetails</c> setting.
/// </summary>
public sealed class WorkflowFailureStreamingTests
{
    private const string AgentName = "failing-workflow";
    private const string ExecutorId = "failing-step";
    private const string GenericErrorMessage = "An error occurred while executing the workflow.";
    private const string ExceptionMessage = "The step could not reach its backing store.";

    [Fact]
    public async Task ExecutorFailedEvent_UsesHostSelectedErrorContentAsync()
    {
        // Arrange
        const string HostMessage = "The step could not be completed.";
        AgentResponseUpdate update = CreateWorkflowUpdate(new ExecutorFailedEvent(ExecutorId, CreateThrownException()), new ErrorContent(HostMessage));

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(update);

        // Assert
        ExecutorActionItemResource item = GetFailedExecutorItem(events);
        Assert.Equal(ExecutorId, item.ExecutorId);
        Assert.Equal(HostMessage, item.Error);
    }

    [Fact]
    public async Task ExecutorFailedEvent_WithoutErrorContent_UsesGenericMessageAsync()
    {
        // Arrange
        AgentResponseUpdate update = CreateWorkflowUpdate(new ExecutorFailedEvent(ExecutorId, CreateThrownException()));

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(update);

        // Assert
        Assert.Equal(GenericErrorMessage, GetFailedExecutorItem(events).Error);
    }

    [Fact]
    public async Task ExecutorFailedEvent_PreservesItemCorrelationAndOrderingAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            CreateWorkflowUpdate(new ExecutorInvokedEvent(ExecutorId, "input")),
            CreateWorkflowUpdate(new ExecutorFailedEvent(ExecutorId, CreateThrownException()), new ErrorContent(GenericErrorMessage))
        ];

        // Act
        List<StreamingResponseEvent> events = await CollectStreamingEventsAsync(updates);

        // Assert
        StreamingOutputItemAdded added = Assert.Single(events.OfType<StreamingOutputItemAdded>());
        StreamingOutputItemDone done = Assert.Single(events.OfType<StreamingOutputItemDone>());
        Assert.Equal(added.Item.Id, done.Item.Id);
        Assert.Equal("failed", Assert.IsType<ExecutorActionItemResource>(done.Item).Status);
        Assert.True(added.SequenceNumber < done.SequenceNumber);
        Assert.IsType<StreamingResponseCompleted>(events[^1]);
    }

    [Theory]
    [InlineData("The workflow could not be completed.", "The workflow could not be completed.")]
    [InlineData(null, GenericErrorMessage)]
    public async Task WorkflowErrorEvent_FailsWithHostSelectedErrorTextAsync(string? hostMessage, string expectedMessage)
    {
        // Arrange
        AIContent[] contents = hostMessage is null ? [] : [new ErrorContent(hostMessage)];
        AgentResponseUpdate update = CreateWorkflowUpdate(new WorkflowErrorEvent(CreateThrownException()), contents);

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => CollectStreamingEventsAsync(update));

        // Assert
        Assert.Equal(expectedMessage, exception.Message);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HostedWorkflowFailure_NonStreaming_ReturnsServerErrorWithHostSelectedTextAsync(bool includeExceptionDetails)
    {
        // Arrange
        await using WebApplication app = await StartWorkflowHostAsync(includeExceptionDetails);
        using HttpClient client = app.GetTestClient();

        // Act
        (HttpStatusCode status, string body) = await PostResponseAsync(client, """{"model":"test","input":"hello","stream":false}""");

        // Assert
        Assert.Equal(HttpStatusCode.InternalServerError, status);
        using JsonDocument document = JsonDocument.Parse(body);
        Assert.Equal("execution_error", document.RootElement.GetProperty("title").GetString());
        Assert.Equal(ExpectedMessage(includeExceptionDetails), document.RootElement.GetProperty("detail").GetString());
        AssertNoExceptionInternals(body, includeExceptionDetails);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HostedWorkflowFailure_Streaming_EndsFailedWithHostSelectedTextAsync(bool includeExceptionDetails)
    {
        // Arrange
        await using WebApplication app = await StartWorkflowHostAsync(includeExceptionDetails);
        using HttpClient client = app.GetTestClient();
        string expectedMessage = ExpectedMessage(includeExceptionDetails);

        // Act
        (HttpStatusCode status, string body) = await PostResponseAsync(client, """{"model":"test","input":"hello","stream":true}""");

        // Assert
        Assert.Equal(HttpStatusCode.OK, status);
        AssertNoExceptionInternals(body, includeExceptionDetails);
        List<JsonElement> events = ParseServerSentEvents(body);
        JsonElement failedItem = events.Single(e =>
            e.GetProperty("type").GetString() == "response.output_item.done" &&
            e.GetProperty("item").GetProperty("status").GetString() == "failed").GetProperty("item");
        Assert.Equal("executor_action", failedItem.GetProperty("type").GetString());
        Assert.Equal(ExecutorId, failedItem.GetProperty("executor_id").GetString());
        Assert.Equal(expectedMessage, failedItem.GetProperty("error").GetString());

        JsonElement terminal = events[^1];
        Assert.Equal("response.failed", terminal.GetProperty("type").GetString());
        AssertFailedResponse(terminal.GetProperty("response"), expectedMessage);

        string responseId = terminal.GetProperty("response").GetProperty("id").GetString()!;
        using HttpResponseMessage stored = await client.GetAsync(new Uri($"/{AgentName}/v1/responses/{responseId}", UriKind.Relative));
        string storedBody = await stored.Content.ReadAsStringAsync();
        Assert.Equal(HttpStatusCode.OK, stored.StatusCode);
        AssertNoExceptionInternals(storedBody, includeExceptionDetails);
        using JsonDocument storedDocument = JsonDocument.Parse(storedBody);
        AssertFailedResponse(storedDocument.RootElement, expectedMessage);

        using HttpResponseMessage replay = await client.GetAsync(new Uri($"/{AgentName}/v1/responses/{responseId}?stream=true", UriKind.Relative));
        string replayBody = await replay.Content.ReadAsStringAsync();
        Assert.Equal(HttpStatusCode.OK, replay.StatusCode);
        Assert.Equal("response.failed", ParseServerSentEvents(replayBody)[^1].GetProperty("type").GetString());
        AssertNoExceptionInternals(replayBody, includeExceptionDetails);
    }

    [Theory(Skip = "Temporarily skipped due to flaky background failure handling; see https://github.com/microsoft/agent-framework/issues/10323")]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HostedWorkflowFailure_Background_StoresFailedResponseWithHostSelectedTextAsync(bool includeExceptionDetails)
    {
        // Arrange
        await using WebApplication app = await StartWorkflowHostAsync(includeExceptionDetails);
        using HttpClient client = app.GetTestClient();

        // Act
        (HttpStatusCode status, string body) = await PostResponseAsync(client, """{"model":"test","input":"hello","stream":false,"background":true}""");
        using JsonDocument created = JsonDocument.Parse(body);
        string responseId = created.RootElement.GetProperty("id").GetString()!;
        string storedBody = await WaitForTerminalResponseAsync(client, responseId);

        // Assert
        Assert.Equal(HttpStatusCode.Accepted, status);
        AssertNoExceptionInternals(storedBody, includeExceptionDetails);
        using JsonDocument stored = JsonDocument.Parse(storedBody);
        AssertFailedResponse(stored.RootElement, ExpectedMessage(includeExceptionDetails));
    }

    private static string ExpectedMessage(bool includeExceptionDetails) =>
        includeExceptionDetails ? ExceptionMessage : GenericErrorMessage;

    private static void AssertFailedResponse(JsonElement response, string expectedMessage)
    {
        Assert.Equal("failed", response.GetProperty("status").GetString());
        Assert.Equal("execution_error", response.GetProperty("error").GetProperty("code").GetString());
        Assert.Equal(expectedMessage, response.GetProperty("error").GetProperty("message").GetString());
        JsonElement failedItem = response.GetProperty("output").EnumerateArray().Single(item =>
            item.GetProperty("type").GetString() == "executor_action" &&
            item.GetProperty("status").GetString() == "failed");
        Assert.Equal(expectedMessage, failedItem.GetProperty("error").GetString());
    }

    private static void AssertNoExceptionInternals(string body, bool includeExceptionDetails)
    {
        Assert.DoesNotContain(typeof(InvalidOperationException).FullName!, body, StringComparison.Ordinal);
        Assert.DoesNotContain(nameof(ThrowingChatExecutor), body, StringComparison.Ordinal);
        Assert.DoesNotContain(nameof(WorkflowFailureStreamingTests), body, StringComparison.Ordinal);
        Assert.DoesNotContain("TargetSite", body, StringComparison.Ordinal);
        if (!includeExceptionDetails)
        {
            Assert.DoesNotContain(ExceptionMessage, body, StringComparison.Ordinal);
        }
    }

    private static async Task<(HttpStatusCode Status, string Body)> PostResponseAsync(HttpClient client, string json)
    {
        using StringContent content = new(json, Encoding.UTF8, "application/json");
        using HttpResponseMessage response = await client.PostAsync(new Uri($"/{AgentName}/v1/responses", UriKind.Relative), content);
        return (response.StatusCode, await response.Content.ReadAsStringAsync());
    }

    private static async Task<string> WaitForTerminalResponseAsync(HttpClient client, string responseId)
    {
        for (int attempt = 0; attempt < 100; attempt++)
        {
            using HttpResponseMessage response = await client.GetAsync(new Uri($"/{AgentName}/v1/responses/{responseId}", UriKind.Relative));
            string body = await response.Content.ReadAsStringAsync();
            using JsonDocument document = JsonDocument.Parse(body);
            if (document.RootElement.GetProperty("status").GetString() is "completed" or "failed" or "cancelled" or "incomplete")
            {
                return body;
            }

            await Task.Delay(50);
        }

        throw new TimeoutException($"Response '{responseId}' did not reach a terminal state.");
    }

    private static async Task<WebApplication> StartWorkflowHostAsync(bool includeExceptionDetails)
    {
        Workflow workflow = new WorkflowBuilder(new ThrowingChatExecutor()).Build();
        AIAgent agent = workflow.AsAIAgent(name: AgentName, includeExceptionDetails: includeExceptionDetails);

        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddKeyedSingleton(AgentName, agent);
        builder.AddOpenAIResponses();

        WebApplication app = builder.Build();
        app.MapOpenAIResponses(agent, responsesPath: null, PermissiveMapOptions.Responses());
        await app.StartAsync();
        return app;
    }

    private static List<JsonElement> ParseServerSentEvents(string body)
    {
        List<JsonElement> events = [];
        foreach (string line in body.Split('\n').Where(line => line.StartsWith("data: ", StringComparison.Ordinal)))
        {
            using JsonDocument document = JsonDocument.Parse(line.Substring("data: ".Length));
            events.Add(document.RootElement.Clone());
        }

        return events;
    }

    private static ExecutorActionItemResource GetFailedExecutorItem(List<StreamingResponseEvent> events)
    {
        ExecutorActionItemResource item = Assert.IsType<ExecutorActionItemResource>(Assert.Single(events.OfType<StreamingOutputItemDone>()).Item);
        Assert.Equal("failed", item.Status);
        return item;
    }

    private static AgentResponseUpdate CreateWorkflowUpdate(WorkflowEvent workflowEvent, params AIContent[] contents) =>
        new(ChatRole.Assistant, contents)
        {
            MessageId = Guid.NewGuid().ToString("N"),
            ResponseId = "resp_workflow",
            RawRepresentation = workflowEvent
        };

    private static InvalidOperationException CreateThrownException()
    {
        try
        {
            throw new InvalidOperationException(ExceptionMessage);
        }
        catch (InvalidOperationException ex)
        {
            return ex;
        }
    }

    private static async Task<List<StreamingResponseEvent>> CollectStreamingEventsAsync(params AgentResponseUpdate[] updates)
    {
        CreateResponse request = new() { Input = ResponseInput.FromText("test"), Model = "test" };
        AgentInvocationContext context = new(new IdGenerator("resp_test", "conv_test"));
        List<StreamingResponseEvent> events = [];
        await foreach (StreamingResponseEvent evt in ToAsyncEnumerableAsync(updates).ToStreamingResponseAsync(request, context))
        {
            events.Add(evt);
        }

        return events;
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(
        IEnumerable<T> values,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (T value in values)
        {
            cancellationToken.ThrowIfCancellationRequested();
            yield return value;
            await Task.Yield();
        }
    }

    private sealed class ThrowingChatExecutor() : Executor(ExecutorId)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder =>
                routeBuilder
                    .AddHandler<IEnumerable<ChatMessage>>((_, _, _) => default)
                    .AddHandler<TurnToken, AgentResponse>(HandleTurnAsync));

        private static ValueTask<AgentResponse> HandleTurnAsync(TurnToken turnToken, IWorkflowContext context, CancellationToken cancellationToken) =>
            throw new InvalidOperationException(ExceptionMessage);
    }
}
