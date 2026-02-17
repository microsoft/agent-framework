// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Behaviors;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Behaviors;

public class BehaviorPipelineTests
{
    [Fact]
    public async Task ExecutorPipeline_WithNoBehaviors_ReturnsFastPathAsync()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();
        var executed = false;

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution
        };

        // Act
        var result = await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            async ct => { executed = true; return await Task.FromResult("result"); },
            CancellationToken.None);

        // Assert
        executed.Should().BeTrue();
        result.Should().Be("result");
    }

    [Fact]
    public async Task ExecutorPipeline_WithSingleBehavior_ExecutesBehaviorAsync()
    {
        // Arrange
        var behaviorExecuted = false;
        var behavior = new TestExecutorBehavior(ctx => behaviorExecuted = true);

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(behavior);
        var pipeline = options.BuildPipeline();

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution
        };

        // Act
        await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            async ct => await Task.FromResult("result"),
            CancellationToken.None);

        // Assert
        behaviorExecuted.Should().BeTrue();
    }

    [Fact]
    public async Task ExecutorPipeline_WithMultipleBehaviors_ExecutesInOrderAsync()
    {
        // Arrange
        var executionOrder = new List<int>();
        var behavior1 = new TestExecutorBehavior(ctx => executionOrder.Add(1));
        var behavior2 = new TestExecutorBehavior(ctx => executionOrder.Add(2));
        var behavior3 = new TestExecutorBehavior(ctx => executionOrder.Add(3));

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(behavior1);
        options.AddExecutorBehavior(behavior2);
        options.AddExecutorBehavior(behavior3);
        var pipeline = options.BuildPipeline();

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution
        };

        // Act
        await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            async ct => await Task.FromResult("result"),
            CancellationToken.None);

        // Assert
        executionOrder.Should().Equal(1, 2, 3);
    }

    [Fact]
    public async Task ExecutorPipeline_BehaviorCanShortCircuit_SkipsRemainingPipelineAsync()
    {
        // Arrange
        var behavior1Executed = false;
        var behavior2Executed = false;
        var coreExecuted = false;

        var behavior1 = new ShortCircuitingExecutorBehavior(() => { behavior1Executed = true; return "short-circuit"; });
        var behavior2 = new TestExecutorBehavior(ctx => behavior2Executed = true);

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(behavior1);
        options.AddExecutorBehavior(behavior2);
        var pipeline = options.BuildPipeline();

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution
        };

        // Act
        var result = await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            async ct => { coreExecuted = true; return await Task.FromResult("core-result"); },
            CancellationToken.None);

        // Assert
        behavior1Executed.Should().BeTrue();
        behavior2Executed.Should().BeFalse();
        coreExecuted.Should().BeFalse();
        result.Should().Be("short-circuit");
    }

    [Fact]
    public async Task ExecutorPipeline_BehaviorThrowsException_WrapsInBehaviorExecutionExceptionAsync()
    {
        // Arrange
        var behavior = new ThrowingExecutorBehavior();

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(behavior);
        var pipeline = options.BuildPipeline();

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution
        };

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            async ct => await Task.FromResult("result"),
            CancellationToken.None);

        // Assert
        await act.Should().ThrowAsync<BehaviorExecutionException>()
            .WithMessage("*ThrowingExecutorBehavior*");
    }

    [Fact]
    public async Task WorkflowPipeline_WithSingleBehavior_ExecutesBehaviorAsync()
    {
        // Arrange
        var behaviorExecuted = false;
        var behavior = new TestWorkflowBehavior(ctx => behaviorExecuted = true);

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(behavior);
        var pipeline = options.BuildPipeline();

        var context = new WorkflowBehaviorContext
        {
            WorkflowName = "test-workflow",
            RunId = Guid.NewGuid().ToString(),
            StartExecutorId = "start",
            Stage = WorkflowStage.Starting
        };

        // Act
        await pipeline!.ExecuteWorkflowPipelineAsync(
            context,
            async ct => await Task.FromResult(0),
            CancellationToken.None);

        // Assert
        behaviorExecuted.Should().BeTrue();
    }

    [Fact]
    public async Task WorkflowPipeline_WithMultipleBehaviors_ExecutesInOrderAsync()
    {
        // Arrange
        var executionOrder = new List<int>();
        var behavior1 = new TestWorkflowBehavior(ctx => executionOrder.Add(1));
        var behavior2 = new TestWorkflowBehavior(ctx => executionOrder.Add(2));
        var behavior3 = new TestWorkflowBehavior(ctx => executionOrder.Add(3));

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(behavior1);
        options.AddWorkflowBehavior(behavior2);
        options.AddWorkflowBehavior(behavior3);
        var pipeline = options.BuildPipeline();

        var context = new WorkflowBehaviorContext
        {
            WorkflowName = "test-workflow",
            RunId = Guid.NewGuid().ToString(),
            StartExecutorId = "start",
            Stage = WorkflowStage.Starting
        };

        // Act
        await pipeline!.ExecuteWorkflowPipelineAsync(
            context,
            async ct => await Task.FromResult(0),
            CancellationToken.None);

        // Assert
        executionOrder.Should().Equal(1, 2, 3);
    }

    [Fact]
    public async Task WorkflowPipeline_BehaviorThrowsException_WrapsInBehaviorExecutionExceptionAsync()
    {
        // Arrange
        var behavior = new ThrowingWorkflowBehavior();

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(behavior);
        var pipeline = options.BuildPipeline();

        var context = new WorkflowBehaviorContext
        {
            WorkflowName = "test-workflow",
            RunId = Guid.NewGuid().ToString(),
            StartExecutorId = "start",
            Stage = WorkflowStage.Starting
        };

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteWorkflowPipelineAsync(
            context,
            async ct => await Task.FromResult(0),
            CancellationToken.None);

        // Assert
        await act.Should().ThrowAsync<BehaviorExecutionException>()
            .WithMessage("*ThrowingWorkflowBehavior*");
    }

    [Fact]
    public void HasExecutorBehaviors_WithBehaviors_ReturnsTrue()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(new TestExecutorBehavior(_ => { }));
        var pipeline = options.BuildPipeline();

        // Act & Assert
        pipeline!.HasExecutorBehaviors.Should().BeTrue();
    }

    [Fact]
    public void HasExecutorBehaviors_WithoutBehaviors_ReturnsFalse()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();

        // Act & Assert
        pipeline!.HasExecutorBehaviors.Should().BeFalse();
    }

    [Fact]
    public void HasWorkflowBehaviors_WithBehaviors_ReturnsTrue()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => { }));
        var pipeline = options.BuildPipeline();

        // Act & Assert
        pipeline!.HasWorkflowBehaviors.Should().BeTrue();
    }

    [Fact]
    public void HasWorkflowBehaviors_WithoutBehaviors_ReturnsFalse()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();

        // Act & Assert
        pipeline!.HasWorkflowBehaviors.Should().BeFalse();
    }

    // Test helper behaviors
    private sealed class TestExecutorBehavior : IExecutorBehavior
    {
        private readonly Action<ExecutorBehaviorContext> _action;

        public TestExecutorBehavior(Action<ExecutorBehaviorContext> action)
        {
            this._action = action;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._action(context);
            return await continuation(cancellationToken);
        }
    }

    private sealed class ShortCircuitingExecutorBehavior : IExecutorBehavior
    {
        private readonly Func<object> _resultFactory;

        public ShortCircuitingExecutorBehavior(Func<object> resultFactory)
        {
            this._resultFactory = resultFactory;
        }

        public ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            // Short-circuit: don't call continuation
            return new ValueTask<object?>(this._resultFactory());
        }
    }

    private sealed class ThrowingExecutorBehavior : IExecutorBehavior
    {
        public ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            throw new InvalidOperationException("Test exception from behavior");
        }
    }

    private sealed class TestWorkflowBehavior : IWorkflowBehavior
    {
        private readonly Action<WorkflowBehaviorContext> _action;

        public TestWorkflowBehavior(Action<WorkflowBehaviorContext> action)
        {
            this._action = action;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            this._action(context);
            return await continuation(cancellationToken);
        }
    }

    private sealed class ThrowingWorkflowBehavior : IWorkflowBehavior
    {
        public ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            throw new InvalidOperationException("Test exception from workflow behavior");
        }
    }
}
