// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using AGUI.Abstractions;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Tests workflow lifecycle and interruption mapping to AG-UI.
/// </summary>
public sealed class WorkflowAGUIExtensionsTests
{
    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorInvokedToStepStartedAsync()
    {
        // Arrange
        AgentResponseUpdate update = CreateUpdate(new ExecutorInvokedEvent("reviewer", "input"));

        // Act
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.RawRepresentation.Should().BeOfType<StepStartedEvent>()
            .Which.StepName.Should().Be("reviewer");
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorCompletedToStepFinishedAsync()
    {
        // Arrange
        AgentResponseUpdate update = CreateUpdate(new ExecutorCompletedEvent("reviewer", "result"));

        // Act
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.RawRepresentation.Should().BeOfType<StepFinishedEvent>()
            .Which.StepName.Should().Be("reviewer");
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_MapsExecutorFailedToStepFinishedAndRunErrorAsync()
    {
        // Arrange
        ErrorContent error = new("An error occurred while executing the workflow.");
        AgentResponseUpdate update = CreateUpdate(
            new ExecutorFailedEvent("reviewer", new InvalidOperationException("internal")),
            error);

        // Act
        List<ChatResponseUpdate> results = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .ToListAsync();

        // Assert
        results.Should().HaveCount(2);
        results[0].RawRepresentation.Should().BeOfType<StepFinishedEvent>()
            .Which.StepName.Should().Be("reviewer");
        results[0].Contents.Should().BeEmpty();
        results[1].RawRepresentation.Should().BeOfType<RunErrorEvent>()
            .Which.Message.Should().Be(error.Message);
        results[1].Contents.Should().BeEmpty();
    }

    [Fact]
    public async Task MakeRunErrorTerminalAsync_EmitsCleanupThenErrorWithoutSuccessAsync()
    {
        // Arrange
        BaseEvent[] events =
        [
            new StepStartedEvent { StepName = "reviewer" },
            new TextMessageStartEvent { MessageId = "message", Role = "assistant" },
            new RunErrorEvent { Message = "failed" },
            new TextMessageStartEvent { MessageId = "orphan", Role = "assistant" },
            new TextMessageEndEvent { MessageId = "orphan" },
            new RunFinishedEvent
            {
                RunId = "run",
                ThreadId = "thread",
                Outcome = new RunFinishedSuccessOutcome(),
            },
        ];

        // Act
        List<BaseEvent> results = await ToAsyncEnumerableAsync(events)
            .MakeRunErrorTerminalAsync()
            .ToListAsync();

        // Assert
        results.Should().HaveCount(5);
        results[^3].Should().BeOfType<TextMessageEndEvent>()
            .Which.MessageId.Should().Be("message");
        results[^2].Should().BeOfType<StepFinishedEvent>()
            .Which.StepName.Should().Be("reviewer");
        results[^1].Should().BeOfType<RunErrorEvent>();
        results.OfType<TextMessageStartEvent>().Should().ContainSingle()
            .Which.MessageId.Should().Be("message");
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_ForwardsOtherUpdatesUnchangedAsync()
    {
        // Arrange
        WorkflowStartedEvent workflowStarted = new("workflow");
        TextContent text = new("hello");
        AgentResponseUpdate update = CreateUpdate(workflowStarted, text);

        // Act
        ChatResponseUpdate convertedUpdate = await ToAsyncEnumerableAsync(update)
            .AsChatResponseUpdatesAsync()
            .SingleAsync();
        ChatResponseUpdate result = await ToAsyncEnumerableAsync(convertedUpdate)
            .MapWorkflowEventsToAGUI()
            .SingleAsync();

        // Assert
        result.Should().BeSameAs(convertedUpdate);
        result.RawRepresentation.Should().BeSameAs(update);
        result.Contents.Should().ContainSingle().Which.Should().BeSameAs(text);
    }

    [Fact]
    public void MapAGUIInterruptResponsesToFunctionResults_MapsResponseUnconditionally()
    {
        // Arrange
        JsonElement payload = JsonSerializer.SerializeToElement(new { approved = true });
        ChatMessage message = new(
            ChatRole.User,
            [new InterruptResponseContent("request-1") { Payload = payload }]);

        // Act
        List<ChatMessage> results = new[] { message }.MapAGUIInterruptResponsesToFunctionResults();

        // Assert
        ChatMessage result = results.Should().ContainSingle().Subject;
        result.Role.Should().Be(ChatRole.User);
        FunctionResultContent functionResult = result.Contents.Should().ContainSingle()
            .Which.Should().BeOfType<FunctionResultContent>().Subject;
        functionResult.CallId.Should().Be("request-1");
        functionResult.Result.Should().Be(payload);
    }

    [Fact]
    public async Task MapWorkflowEventsToAGUI_PrefersWorkflowCorrelatedApprovalRequestAsync()
    {
        // Arrange
        FunctionCallContent toolCall = new(
            "call-1",
            "SubmitExpense",
            new Dictionary<string, object?>());
        ToolApprovalRequestContent originalRequest = new("agent-request", toolCall);
        ToolApprovalRequestContent correlatedRequest = new("workflow-request", toolCall);
        AgentResponseUpdate original = CreateUpdate(raw: new object(), originalRequest);
        AgentResponseUpdate correlated = CreateUpdate(
            new RequestInfoEvent(ExternalRequest.Create(
                RequestPort.Create<ToolApprovalRequestContent, ToolApprovalResponseContent>("approval"),
                originalRequest,
                "workflow-request")),
            correlatedRequest);

        // Act
        List<ChatResponseUpdate> results = await ToAsyncEnumerableAsync([original, correlated])
            .AsChatResponseUpdatesAsync()
            .MapWorkflowEventsToAGUI()
            .ToListAsync();

        // Assert
        ToolApprovalRequestContent request = results.SelectMany(static update => update.Contents)
            .OfType<ToolApprovalRequestContent>()
            .Should().ContainSingle().Subject;
        request.RequestId.Should().Be("workflow-request");
    }

    private static AgentResponseUpdate CreateUpdate(object raw, params AIContent[] contents)
        => new(ChatRole.Assistant, contents)
        {
            AuthorName = "author",
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = "message",
            RawRepresentation = raw,
            ResponseId = "response",
        };

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(
        AgentResponseUpdate update)
    {
        await Task.Yield();
        yield return update;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToAsyncEnumerableAsync(
        IEnumerable<AgentResponseUpdate> updates)
    {
        await Task.Yield();
        foreach (AgentResponseUpdate update in updates)
        {
            yield return update;
        }
    }

    private static async IAsyncEnumerable<ChatResponseUpdate> ToAsyncEnumerableAsync(
        ChatResponseUpdate update)
    {
        await Task.Yield();
        yield return update;
    }

    private static async IAsyncEnumerable<BaseEvent> ToAsyncEnumerableAsync(
        IEnumerable<BaseEvent> events)
    {
        await Task.Yield();
        foreach (BaseEvent evt in events)
        {
            yield return evt;
        }
    }
}
