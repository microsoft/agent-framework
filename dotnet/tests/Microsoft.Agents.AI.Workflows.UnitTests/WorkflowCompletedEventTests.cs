// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Sample;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class WorkflowCompletedEventTests
{
    [Fact]
    public void WorkflowCompletedEvent_WithResult_SetsData()
    {
        var evt = new WorkflowCompletedEvent("done");

        evt.Data.Should().Be("done");
        evt.Should().BeAssignableTo<WorkflowEvent>();
    }

    [Fact]
    public void WorkflowCompletedEvent_WithoutResult_HasNullData()
    {
        var evt = new WorkflowCompletedEvent();

        evt.Data.Should().BeNull();
    }

    [Fact]
    public void WorkflowFailedEvent_HasErrorMessage()
    {
        var evt = new WorkflowFailedEvent("something broke");

        evt.ErrorMessage.Should().Be("something broke");
        evt.Data.Should().Be("something broke");
        evt.Should().BeAssignableTo<WorkflowEvent>();
        evt.Should().NotBeAssignableTo<WorkflowErrorEvent>();
    }

    [Fact]
    public async Task WorkflowCompletedEvent_IsLastEvent_OffThreadAsync()
    {
        // Arrange
        ForwardMessageExecutor<string> executorA = new("A");
        ForwardMessageExecutor<string> executorB = new("B");

        Workflow workflow = new WorkflowBuilder(executorA)
            .AddEdge(executorA, executorB)
            .Build();

        // Act
        await using StreamingRun run = await InProcessExecution.OffThread
            .RunStreamingAsync(workflow, "hello");

        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        events.Should().NotBeEmpty();
        events.Last().Should().BeOfType<WorkflowCompletedEvent>();
        events.OfType<ExecutorCompletedEvent>().Should().NotBeEmpty(
            "there should be executor events before the workflow completion event");
    }

    [Fact]
    public async Task WorkflowCompletedEvent_IsLastEvent_LockstepAsync()
    {
        // Arrange
        ForwardMessageExecutor<string> executorA = new("A");
        ForwardMessageExecutor<string> executorB = new("B");

        Workflow workflow = new WorkflowBuilder(executorA)
            .AddEdge(executorA, executorB)
            .Build();

        // Act
        await using StreamingRun run = await InProcessExecution.Lockstep
            .RunStreamingAsync(workflow, "hello");

        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        events.Should().NotBeEmpty();
        events.Last().Should().BeOfType<WorkflowCompletedEvent>();
        events.OfType<ExecutorCompletedEvent>().Should().NotBeEmpty(
            "there should be executor events before the workflow completion event");
    }

    [Fact]
    public async Task WorkflowFailedEvent_CanBeEmittedByExecutorAsync()
    {
        // Arrange
        FailingExecutor executor = new("Failing");

        Workflow workflow = new WorkflowBuilder(executor).Build();

        // Act
        await using StreamingRun run = await InProcessExecution.OffThread
            .RunStreamingAsync(workflow, "trigger");

        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            events.Add(evt);
        }

        // Assert
        events.OfType<WorkflowFailedEvent>().Should().ContainSingle()
            .Which.ErrorMessage.Should().Be("custom error from executor");
    }

    [Fact]
    public async Task WorkflowCompletedEvent_NotEmitted_WhenPendingRequests_LockstepAsync()
    {
        // Arrange: Use a workflow that makes external requests (guessing game from Sample 04).
        // The RequestPort is the entry executor — it immediately posts an external request
        // and the workflow pauses with RunStatus.PendingRequests.
        Workflow workflow = Step4EntryPoint.WorkflowInstance;

        // Act: Run in lockstep mode with blockOnPendingRequest: false so the stream exits
        // when the workflow pauses instead of waiting for a response.
        await using StreamingRun run = await InProcessExecution.Lockstep
            .RunStreamingAsync(workflow, NumberSignal.Init);

        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false))
        {
            events.Add(evt);
        }

        // Assert: The workflow is paused (not completed), so WorkflowCompletedEvent should NOT appear.
        events.Should().NotContain(e => e is WorkflowCompletedEvent,
            "WorkflowCompletedEvent should not be emitted when the workflow is paused with pending requests");
        events.OfType<RequestInfoEvent>().Should().NotBeEmpty(
            "workflow should have emitted at least one external request before pausing");
    }

    [Fact]
    public async Task WorkflowCompletedEvent_NotEmitted_WhenPendingRequests_OffThreadAsync()
    {
        // Arrange: Same workflow, but verify the streaming (off-thread) path is also correct.
        Workflow workflow = Step4EntryPoint.WorkflowInstance;

        // Act
        await using StreamingRun run = await InProcessExecution.OffThread
            .RunStreamingAsync(workflow, NumberSignal.Init);

        List<WorkflowEvent> events = [];
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false))
        {
            events.Add(evt);
        }

        // Assert
        events.Should().NotContain(e => e is WorkflowCompletedEvent,
            "WorkflowCompletedEvent should not be emitted when the workflow is paused with pending requests");
        events.OfType<RequestInfoEvent>().Should().NotBeEmpty(
            "workflow should have emitted at least one external request before pausing");
    }
}

/// <summary>
/// An executor that emits a <see cref="WorkflowFailedEvent"/> and then requests halt.
/// </summary>
internal sealed class FailingExecutor(string id) : Executor(id)
{
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        protocolBuilder.RouteBuilder.AddHandler<string>(async (message, ctx) =>
        {
            await ctx.AddEventAsync(new WorkflowFailedEvent("custom error from executor"));
            await ctx.RequestHaltAsync();
        });

        return protocolBuilder;
    }
}
