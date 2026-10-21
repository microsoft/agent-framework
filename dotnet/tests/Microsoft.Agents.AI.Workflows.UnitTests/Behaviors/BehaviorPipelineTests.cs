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
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
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
    public async Task ExecutorPipeline_WithNoBehaviors_FinalHandlerExceptionNotWrappedAsync()
    {
        // Arrange - no behaviors registered, so exceptions from the core handler should not be wrapped
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();

        var context = new ExecutorBehaviorContext
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
        };

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteExecutorPipelineAsync(
            context,
            ct => throw new InvalidOperationException("Core handler error"),
            CancellationToken.None);

        // Assert - the raw exception propagates without being wrapped in BehaviorExecutionException
        await act.Should().ThrowAsync<InvalidOperationException>()
            .WithMessage("Core handler error");
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
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
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
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
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
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
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
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
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

    [Fact]
    public async Task WorkflowPipeline_WithNoBehaviors_ReturnsFastPathAsync()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();
        var executed = false;

        // Act
        var result = await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            async ct => { executed = true; return await Task.FromResult(42); },
            CancellationToken.None);

        // Assert
        executed.Should().BeTrue();
        result.Should().Be(42);
    }

    [Fact]
    public async Task WorkflowPipeline_WithNoBehaviors_FinalHandlerExceptionNotWrappedAsync()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteWorkflowPipelineAsync<int>(
            CreateWorkflowContext(),
            ct => throw new InvalidOperationException("Core handler error"),
            CancellationToken.None);

        // Assert - without behaviors the raw exception propagates unwrapped
        await act.Should().ThrowAsync<InvalidOperationException>().WithMessage("Core handler error");
    }

    [Fact]
    public async Task WorkflowPipeline_ReturnsFinalHandlerResultThroughBehaviorsAsync()
    {
        // Arrange - TResult must survive the trip through the behavior chain
        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => { }));
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => { }));
        var pipeline = options.BuildPipeline();

        // Act
        var result = await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            async ct => await Task.FromResult("handler-result"),
            CancellationToken.None);

        // Assert
        result.Should().Be("handler-result");
    }

    [Fact]
    public async Task WorkflowPipeline_BehaviorCanShortCircuit_SkipsRemainingPipelineAsync()
    {
        // Arrange
        var innerRan = false;
        var finalHandlerRan = false;

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new ShortCircuitingWorkflowBehavior("short-circuited"));
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => innerRan = true));
        var pipeline = options.BuildPipeline();

        // Act
        var result = await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            async ct => { finalHandlerRan = true; return await Task.FromResult("handler-result"); },
            CancellationToken.None);

        // Assert - neither the inner behavior nor the final handler runs
        result.Should().Be("short-circuited");
        innerRan.Should().BeFalse();
        finalHandlerRan.Should().BeFalse();
    }

    [Fact]
    public async Task WorkflowPipeline_VoidOverload_ExecutesBehaviorsAndFinalHandlerAsync()
    {
        // Arrange - the non-generic overload is what InProcessRunner uses for Starting/Ending
        var executionOrder = new List<string>();

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => executionOrder.Add("behavior1")));
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => executionOrder.Add("behavior2")));
        var pipeline = options.BuildPipeline();

        // Act
        await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            ct => { executionOrder.Add("final"); return default; },
            CancellationToken.None);

        // Assert
        executionOrder.Should().Equal("behavior1", "behavior2", "final");
    }

    [Fact]
    public async Task WorkflowPipeline_VoidOverload_WithNoBehaviors_ExecutesFinalHandlerAsync()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        var pipeline = options.BuildPipeline();
        var executed = false;

        // Act
        await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            ct => { executed = true; return default; },
            CancellationToken.None);

        // Assert
        executed.Should().BeTrue();
    }

    [Fact]
    public async Task ExecutorPipeline_BehaviorExecutionException_IsNotDoubleWrappedAsync()
    {
        // Arrange - an inner behavior's already-wrapped failure must not be re-wrapped by outer behaviors
        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(new TestExecutorBehavior(_ => { }));
        options.AddExecutorBehavior(new ThrowingExecutorBehavior());
        var pipeline = options.BuildPipeline();

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteExecutorPipelineAsync(
            CreateExecutorContext(),
            async ct => await Task.FromResult<object?>("result"),
            CancellationToken.None);

        // Assert - exactly one layer of wrapping, with the original exception underneath
        var wrapped = (await act.Should().ThrowAsync<BehaviorExecutionException>()).Which;
        wrapped.BehaviorType.Should().Contain(nameof(ThrowingExecutorBehavior));
        wrapped.InnerException.Should().BeOfType<InvalidOperationException>();
    }

    [Fact]
    public async Task WorkflowPipeline_BehaviorExecutionException_IsNotDoubleWrappedAsync()
    {
        // Arrange
        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new TestWorkflowBehavior(_ => { }));
        options.AddWorkflowBehavior(new ThrowingWorkflowBehavior());
        var pipeline = options.BuildPipeline();

        // Act
        Func<Task> act = async () => await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            async ct => await Task.FromResult(0),
            CancellationToken.None);

        // Assert
        var wrapped = (await act.Should().ThrowAsync<BehaviorExecutionException>()).Which;
        wrapped.BehaviorType.Should().Contain(nameof(ThrowingWorkflowBehavior));
        wrapped.InnerException.Should().BeOfType<InvalidOperationException>();
    }

    [Fact]
    public async Task ExecutorPipeline_CancellationTokenIsPropagatedToBehaviorsAndHandlerAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        CancellationToken observedByBehavior = default;
        CancellationToken observedByHandler = default;

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(new TokenCapturingExecutorBehavior(ct => observedByBehavior = ct));
        var pipeline = options.BuildPipeline();

        // Act
        await pipeline!.ExecuteExecutorPipelineAsync(
            CreateExecutorContext(),
            async ct => { observedByHandler = ct; return await Task.FromResult<object?>("result"); },
            cts.Token);

        // Assert
        observedByBehavior.Should().Be(cts.Token);
        observedByHandler.Should().Be(cts.Token);
    }

    [Fact]
    public async Task WorkflowPipeline_CancellationTokenIsPropagatedToBehaviorsAndHandlerAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        CancellationToken observedByBehavior = default;
        CancellationToken observedByHandler = default;

        var options = new WorkflowBehaviorOptions();
        options.AddWorkflowBehavior(new TokenCapturingWorkflowBehavior(ct => observedByBehavior = ct));
        var pipeline = options.BuildPipeline();

        // Act
        await pipeline!.ExecuteWorkflowPipelineAsync(
            CreateWorkflowContext(),
            async ct => { observedByHandler = ct; return await Task.FromResult(0); },
            cts.Token);

        // Assert
        observedByBehavior.Should().Be(cts.Token);
        observedByHandler.Should().Be(cts.Token);
    }

    [Fact]
    public async Task ExecutorPipeline_BehaviorTransformsResult_ReturnsTransformedValueAsync()
    {
        // Arrange - behaviors may rewrite the handler's result on the way out
        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(new ResultTransformingExecutorBehavior(r => $"outer({r})"));
        options.AddExecutorBehavior(new ResultTransformingExecutorBehavior(r => $"inner({r})"));
        var pipeline = options.BuildPipeline();

        // Act
        var result = await pipeline!.ExecuteExecutorPipelineAsync(
            CreateExecutorContext(),
            async ct => await Task.FromResult<object?>("core"),
            CancellationToken.None);

        // Assert - the innermost behavior transforms first, the outermost last
        result.Should().Be("outer(inner(core))");
    }

    [Fact]
    public async Task ExecutorPipeline_MultipleBehaviors_NestInRegistrationOrderAsync()
    {
        // Arrange - the first registered behavior should be outermost: first in, last out
        var log = new List<string>();

        var options = new WorkflowBehaviorOptions();
        options.AddExecutorBehavior(new NestingExecutorBehavior("A", log));
        options.AddExecutorBehavior(new NestingExecutorBehavior("B", log));
        var pipeline = options.BuildPipeline();

        // Act
        await pipeline!.ExecuteExecutorPipelineAsync(
            CreateExecutorContext(),
            async ct => { log.Add("handler"); return await Task.FromResult<object?>("result"); },
            CancellationToken.None);

        // Assert
        log.Should().Equal("A:enter", "B:enter", "handler", "B:exit", "A:exit");
    }

    private static WorkflowBehaviorContext CreateWorkflowContext(WorkflowStage stage = WorkflowStage.Starting) =>
        new()
        {
            WorkflowName = "test-workflow",
            RunId = Guid.NewGuid().ToString(),
            StartExecutorId = "start",
            Stage = stage
        };

    private static ExecutorBehaviorContext CreateExecutorContext() =>
        new()
        {
            ExecutorId = "test-executor",
            ExecutorType = typeof(BehaviorPipelineTests),
            Message = "test",
            MessageType = typeof(string),
            RunId = Guid.NewGuid().ToString(),
            Stage = ExecutorStage.PreExecution,
            WorkflowContext = NullWorkflowContext.Instance
        };

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

    private sealed class ShortCircuitingWorkflowBehavior : IWorkflowBehavior
    {
        private readonly object _result;

        public ShortCircuitingWorkflowBehavior(object result)
        {
            this._result = result;
        }

        public ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            // Short-circuit: don't call continuation
            return new ValueTask<TResult>((TResult)this._result);
        }
    }

    private sealed class TokenCapturingExecutorBehavior : IExecutorBehavior
    {
        private readonly Action<CancellationToken> _capture;

        public TokenCapturingExecutorBehavior(Action<CancellationToken> capture)
        {
            this._capture = capture;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._capture(cancellationToken);
            return await continuation(cancellationToken);
        }
    }

    private sealed class TokenCapturingWorkflowBehavior : IWorkflowBehavior
    {
        private readonly Action<CancellationToken> _capture;

        public TokenCapturingWorkflowBehavior(Action<CancellationToken> capture)
        {
            this._capture = capture;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            this._capture(cancellationToken);
            return await continuation(cancellationToken);
        }
    }

    private sealed class ResultTransformingExecutorBehavior : IExecutorBehavior
    {
        private readonly Func<object?, object?> _transform;

        public ResultTransformingExecutorBehavior(Func<object?, object?> transform)
        {
            this._transform = transform;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            var result = await continuation(cancellationToken);
            return this._transform(result);
        }
    }

    private sealed class NestingExecutorBehavior : IExecutorBehavior
    {
        private readonly string _name;
        private readonly List<string> _log;

        public NestingExecutorBehavior(string name, List<string> log)
        {
            this._name = name;
            this._log = log;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._log.Add($"{this._name}:enter");
            var result = await continuation(cancellationToken);
            this._log.Add($"{this._name}:exit");
            return result;
        }
    }

    private sealed class NullWorkflowContext : IWorkflowContext
    {
        public static readonly NullWorkflowContext Instance = new();

        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default) => default;
        public ValueTask SendMessageAsync(object message, string? targetId, CancellationToken cancellationToken = default) => default;
        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default) => default;
        public ValueTask RequestHaltAsync() => default;
        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default) => default;
        public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default) => new(initialStateFactory());
        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default) => new(new HashSet<string>());
        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default) => default;
        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default) => default;
        public IReadOnlyDictionary<string, string>? TraceContext => null;
        public bool ConcurrentRunsEnabled => false;
    }
}
