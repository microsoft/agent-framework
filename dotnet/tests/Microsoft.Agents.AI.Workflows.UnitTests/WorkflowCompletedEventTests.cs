// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;

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
