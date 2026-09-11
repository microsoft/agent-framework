// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Behaviors;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.InProc;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Behaviors;

/// <summary>
/// End-to-end tests that validate pipeline behaviors work with actual workflows.
/// </summary>
public class WorkflowBehaviorEndToEndTests
{
    [Fact]
    public async Task Workflow_WithExecutorBehavior_BehaviorExecutesBeforeAndAfterExecutorAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var behavior = new LoggingExecutorBehavior(executionLog);

        var executor1 = new LoggingExecutor("executor1", executionLog);
        var executor2 = new LoggingExecutor("executor2", executionLog);

        var workflow = new WorkflowBuilder(executor1)
            .WithBehaviors(options => options.AddExecutorBehavior(behavior))
            .AddEdge(executor1, executor2)
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert
        executionLog.Should().ContainInOrder(
            "Behavior:PreExecution:executor1",
            "Executor:executor1",
            "Behavior:PreExecution:executor2",
            "Executor:executor2"
        );
    }

    [Fact]
    public async Task Workflow_WithWorkflowBehavior_BehaviorExecutesAtStartAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var behavior = new LoggingWorkflowBehavior(executionLog);

        var executor = new LoggingExecutor("executor", executionLog);

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddWorkflowBehavior(behavior))
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - workflow start behavior should execute before executor
        executionLog.Should().Contain("WorkflowBehavior:Starting");
        executionLog.Should().Contain("Executor:executor");

        var startIndex = executionLog.IndexOf("WorkflowBehavior:Starting");
        var executorIndex = executionLog.IndexOf("Executor:executor");
        startIndex.Should().BeLessThan(executorIndex);
    }

    [Fact]
    public async Task Workflow_WithWorkflowBehavior_BehaviorExecutesAtEndAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var behavior = new LoggingWorkflowBehavior(executionLog);
        var executor = new SimpleExecutor("executor");

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddWorkflowBehavior(behavior))
            .Build();

        // Act - dispose triggers the Ending stage
        await using (await InProcessExecution.RunAsync(workflow, "test-input"))
        {
        }

        // Assert - both Starting and Ending stages should execute, in order
        executionLog.Should().Contain("WorkflowBehavior:Starting");
        executionLog.Should().Contain("WorkflowBehavior:Ending");

        var startIndex = executionLog.IndexOf("WorkflowBehavior:Starting");
        var endIndex = executionLog.IndexOf("WorkflowBehavior:Ending");
        startIndex.Should().BeLessThan(endIndex);
    }

    [Fact]
    public async Task Workflow_WithBothBehaviorTypes_ExecutesInCorrectOrderAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var workflowBehavior = new LoggingWorkflowBehavior(executionLog);
        var executorBehavior = new LoggingExecutorBehavior(executionLog);
        var executor = new LoggingExecutor("executor", executionLog);

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddWorkflowBehavior(workflowBehavior);
                options.AddExecutorBehavior(executorBehavior);
            })
            .Build();

        // Act
        await using (await InProcessExecution.RunAsync(workflow, "test-input"))
        {
        }

        // Assert - Starting → PreExecution (with executor) → Ending
        executionLog.Should().ContainInOrder(
            "WorkflowBehavior:Starting",
            "Behavior:PreExecution:executor",
            "Executor:executor",
            "WorkflowBehavior:Ending"
        );
    }

    [Fact]
    public async Task Workflow_WithBehaviors_RunIdIsConsistentAcrossContextsAsync()
    {
        // Arrange
        string? workflowBehaviorRunId = null;
        string? executorBehaviorRunId = null;

        var workflowBehavior = new CapturingWorkflowBehavior(ctx => workflowBehaviorRunId = ctx.RunId);
        var executorBehavior = new CapturingExecutorBehavior(ctx => executorBehaviorRunId = ctx.RunId);

        var executor = new SimpleExecutor("executor");
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddWorkflowBehavior(workflowBehavior);
                options.AddExecutorBehavior(executorBehavior);
            })
            .Build();

        // Act
        string runId;
        await using (var run = await InProcessExecution.RunAsync(workflow, "test-input"))
        {
            runId = run.SessionId;
        }

        // Assert - all behavior contexts share the same RunId as the run itself
        workflowBehaviorRunId.Should().NotBeNullOrEmpty();
        executorBehaviorRunId.Should().NotBeNullOrEmpty();
        workflowBehaviorRunId.Should().Be(runId);
        executorBehaviorRunId.Should().Be(runId);
    }

    [Fact]
    public async Task Workflow_WithMultipleBehaviors_AllBehaviorsExecuteAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var loggingBehavior = new LoggingExecutorBehavior(executionLog);
        var validationBehavior = new ValidationExecutorBehavior(executionLog);

        var executor = new LoggingExecutor("executor", executionLog);

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddExecutorBehavior(loggingBehavior);
                options.AddExecutorBehavior(validationBehavior);
            })
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - both behaviors should execute
        executionLog.Should().Contain("Behavior:PreExecution:executor");
        executionLog.Should().Contain("Validation:PreExecution:executor");
        executionLog.Should().Contain("Executor:executor");
    }

    [Fact]
    public async Task Workflow_WithPerformanceMonitoringBehavior_MeasuresExecutionTimeAsync()
    {
        // Arrange
        var measurements = new Dictionary<string, long>();
        var behavior = new PerformanceMonitoringBehavior(measurements);

        var executor = new DelayExecutor("slow-executor", TimeSpan.FromMilliseconds(50));

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(behavior))
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert
        measurements.Should().ContainKey("slow-executor");
        measurements["slow-executor"].Should().BeGreaterThanOrEqualTo(50);
    }

    [Fact]
    public async Task Workflow_WithoutBehaviors_ExecutesNormallyAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var executor = new LoggingExecutor("executor", executionLog);

        var workflow = new WorkflowBuilder(executor).Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - workflow executes normally without behaviors
        executionLog.Should().Contain("Executor:executor");
    }

    [Fact]
    public async Task Workflow_BehaviorShortCircuits_ExecutorDoesNotRunAsync()
    {
        // Arrange
        var executionLog = new List<string>();
        var shortCircuitBehavior = new ShortCircuitBehavior("short-circuit-result");

        var executor = new LoggingExecutor("executor", executionLog);

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(shortCircuitBehavior))
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - executor should not execute due to short-circuit
        executionLog.Should().BeEmpty();
    }

    [Fact]
    public async Task Workflow_BehaviorThrowsException_EmitsErrorEventAsync()
    {
        // Arrange
        var faultyBehavior = new FaultyBehavior();
        var executor = new SimpleExecutor("executor");

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(faultyBehavior))
            .Build();

        // Act - exceptions from behaviors are caught and emitted as WorkflowErrorEvent, not thrown
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert
        var behaviorException = run.OutgoingEvents.OfType<WorkflowErrorEvent>()
            .Should().ContainSingle().Which.Exception
            .Should().BeOfType<BehaviorExecutionException>().Subject;

        behaviorException.BehaviorType.Should().Contain(nameof(FaultyBehavior));
        behaviorException.Stage.Should().Be(nameof(ExecutorStage.PreExecution));
    }

    [Fact]
    public async Task Workflow_WithExecutorBehaviors_PropertiesFlowBetweenBehaviorsAsync()
    {
        // Arrange - an outer behavior enriches the context, an inner behavior reads what it wrote
        object? observedByInner = null;
        var enriching = new EnrichingExecutorBehavior("tenant-id", "contoso");
        var reading = new CapturingExecutorBehavior(
            ctx => observedByInner = ctx.Properties.TryGetValue("tenant-id", out var value) ? value : null);

        var executor = new SimpleExecutor("executor");
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddExecutorBehavior(enriching);
                options.AddExecutorBehavior(reading);
            })
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - the property bag is framework-initialized and shared down the chain
        observedByInner.Should().Be("contoso");
    }

    [Fact]
    public async Task Workflow_EndingBehaviorThrows_ExecutorsAreStillDisposedAsync()
    {
        // Arrange
        var disposedExecutors = new List<string>();
        var faultyBehavior = new FaultyEndingWorkflowBehavior();
        var asyncExecutor = new DisposableExecutor("async-disposable", disposedExecutors);
        var syncExecutor = new SyncDisposableExecutor("sync-disposable", disposedExecutors);

        var workflow = new WorkflowBuilder(asyncExecutor)
            .WithBehaviors(options => options.AddWorkflowBehavior(faultyBehavior))
            .AddEdge(asyncExecutor, syncExecutor)
            .Build();

        var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Act - the Ending stage runs during disposal
        Func<Task> disposeRun = async () => await run.DisposeAsync();

        // Assert - the failure is surfaced to the caller...
        await disposeRun.Should().ThrowAsync<BehaviorExecutionException>();

        // ...but teardown still ran to completion, so executors were disposed rather than leaked.
        disposedExecutors.Should().Contain("async-disposable");
        disposedExecutors.Should().Contain("sync-disposable");
    }

    [Fact]
    public async Task Workflow_ExecutorBehaviorContext_IsFullyPopulatedAsync()
    {
        // Arrange
        ExecutorBehaviorContext? captured = null;
        var behavior = new CapturingExecutorBehavior(ctx => captured ??= ctx);

        var executor = new SimpleExecutor("the-executor");
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddExecutorBehavior(behavior))
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - every context field the public API advertises is populated
        captured.Should().NotBeNull();
        captured!.ExecutorId.Should().Be("the-executor");
        captured.ExecutorType.Should().Be<SimpleExecutor>();
        captured.Message.Should().Be("test-input");
        captured.MessageType.Should().Be<string>();
        captured.Stage.Should().Be(ExecutorStage.PreExecution);
        captured.WorkflowContext.Should().NotBeNull();
        captured.RunId.Should().NotBeNullOrEmpty();
        captured.Properties.Should().NotBeNull();
    }

    [Fact]
    public async Task Workflow_WorkflowBehaviorContext_IsFullyPopulatedAsync()
    {
        // Arrange
        WorkflowBehaviorContext? captured = null;
        var behavior = new CapturingWorkflowBehavior(ctx => captured ??= ctx);

        var executor = new SimpleExecutor("start-executor");
        var workflow = new WorkflowBuilder(executor)
            .WithName("my-workflow")
            .WithDescription("my-description")
            .WithBehaviors(options => options.AddWorkflowBehavior(behavior))
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert
        captured.Should().NotBeNull();
        captured!.WorkflowName.Should().Be("my-workflow");
        captured.WorkflowDescription.Should().Be("my-description");
        captured.StartExecutorId.Should().Be("start-executor");
        captured.Stage.Should().Be(WorkflowStage.Starting);
        captured.RunId.Should().NotBeNullOrEmpty();
        captured.Properties.Should().NotBeNull();
    }

    [Fact]
    public async Task Workflow_WorkflowBehaviorProperties_AreIsolatedBetweenStagesAsync()
    {
        // Arrange - Starting and Ending are separate pipeline passes with separate contexts
        bool? endingSawStartingValue = null;
        var behavior = new StagePropertyBehavior(saw => endingSawStartingValue = saw);

        var executor = new SimpleExecutor("executor");
        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options => options.AddWorkflowBehavior(behavior))
            .Build();

        // Act - disposal triggers the Ending stage
        await using (await InProcessExecution.RunAsync(workflow, "test-input"))
        {
        }

        // Assert - values written during Starting do not leak into Ending
        endingSawStartingValue.Should().BeFalse();
    }

    [Fact]
    public async Task Workflow_ExecutorBehaviorProperties_AreIsolatedBetweenInvocationsAsync()
    {
        // Arrange - each executor invocation gets a fresh property bag
        var sawExistingValue = new List<bool>();
        var behavior = new PerInvocationPropertyBehavior(sawExistingValue);

        var executor1 = new SimpleExecutor("executor1");
        var executor2 = new SimpleExecutor("executor2");
        var workflow = new WorkflowBuilder(executor1)
            .WithBehaviors(options => options.AddExecutorBehavior(behavior))
            .AddEdge(executor1, executor2)
            .Build();

        // Act
        await using var run = await InProcessExecution.RunAsync(workflow, "test-input");

        // Assert - two invocations, neither of which observed the other's value
        sawExistingValue.Should().HaveCountGreaterThanOrEqualTo(2);
        sawExistingValue.Should().AllSatisfy(saw => saw.Should().BeFalse());
    }

    [Fact]
    public async Task Workflow_EndingBehaviors_RunInRegistrationOrderAsync()
    {
        // Arrange - Ending is a separate pass, not an unwinding of Starting
        var executionLog = new List<string>();
        var executor = new SimpleExecutor("executor");

        var workflow = new WorkflowBuilder(executor)
            .WithBehaviors(options =>
            {
                options.AddWorkflowBehavior(new NamedWorkflowBehavior("first", executionLog));
                options.AddWorkflowBehavior(new NamedWorkflowBehavior("second", executionLog));
            })
            .Build();

        // Act
        await using (await InProcessExecution.RunAsync(workflow, "test-input"))
        {
        }

        // Assert - both stages are entered in registration order
        executionLog.Should().Equal(
            "first:Starting",
            "second:Starting",
            "first:Ending",
            "second:Ending");
    }

    [Fact]
    public void RunnerContext_SetRunEndingCallback_CalledTwice_Throws()
    {
        // Arrange - the runner registers exactly one Ending callback; a second must not silently overwrite it
        var workflow = new WorkflowBuilder(new SimpleExecutor("executor")).Build();
        var context = new InProcessRunnerContext(
            workflow,
            sessionId: "test-session",
            checkpointingEnabled: false,
            outgoingEvents: new ConcurrentEventSink(),
            stepTracer: null);

        context.SetRunEndingCallback(_ => default);

        // Act
        Action act = () => context.SetRunEndingCallback(_ => default);

        // Assert
        act.Should().Throw<InvalidOperationException>()
            .WithMessage("*already been registered*");
    }

    // Test Executors
    private sealed class LoggingExecutor : Executor
    {
        private readonly List<string> _log;

        public LoggingExecutor(string id, List<string> log) : base(id)
        {
            this._log = log;
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context, ct) =>
            {
                this._log.Add($"Executor:{this.Id}");
                await context.SendMessageAsync(message, ct);
                return message;
            }));
    }

    private sealed class SimpleExecutor : Executor
    {
        public SimpleExecutor(string id) : base(id) { }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context, ct) =>
            {
                await context.SendMessageAsync(message, ct);
                return message;
            }));
    }

    private sealed class DisposableExecutor : Executor, IAsyncDisposable
    {
        private readonly List<string> _disposed;

        public DisposableExecutor(string id, List<string> disposed) : base(id)
        {
            this._disposed = disposed;
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context, ct) =>
            {
                await context.SendMessageAsync(message, ct);
                return message;
            }));

        public ValueTask DisposeAsync()
        {
            this._disposed.Add(this.Id);
            return default;
        }
    }

    private sealed class SyncDisposableExecutor : Executor, IDisposable
    {
        private readonly List<string> _disposed;

        public SyncDisposableExecutor(string id, List<string> disposed) : base(id)
        {
            this._disposed = disposed;
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context, ct) =>
            {
                await context.SendMessageAsync(message, ct);
                return message;
            }));

        public void Dispose() => this._disposed.Add(this.Id);
    }

    private sealed class DelayExecutor : Executor
    {
        private readonly TimeSpan _delay;

        public DelayExecutor(string id, TimeSpan delay) : base(id)
        {
            this._delay = delay;
        }

        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder) =>
            protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string, string>(async (message, context, ct) =>
            {
                await Task.Delay(this._delay, ct);
                await context.SendMessageAsync(message, ct);
                return message;
            }));
    }

    // Test Behaviors
    private sealed class LoggingExecutorBehavior : IExecutorBehavior
    {
        private readonly List<string> _log;

        public LoggingExecutorBehavior(List<string> log)
        {
            this._log = log;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._log.Add($"Behavior:{context.Stage}:{context.ExecutorId}");
            return await continuation(cancellationToken);
        }
    }

    private sealed class LoggingWorkflowBehavior : IWorkflowBehavior
    {
        private readonly List<string> _log;

        public LoggingWorkflowBehavior(List<string> log)
        {
            this._log = log;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            this._log.Add($"WorkflowBehavior:{context.Stage}");
            return await continuation(cancellationToken);
        }
    }

    private sealed class EnrichingExecutorBehavior : IExecutorBehavior
    {
        private readonly string _key;
        private readonly object _value;

        public EnrichingExecutorBehavior(string key, object value)
        {
            this._key = key;
            this._value = value;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            context.Properties[this._key] = this._value;
            return await continuation(cancellationToken);
        }
    }

    private sealed class StagePropertyBehavior : IWorkflowBehavior
    {
        private readonly Action<bool> _reportEndingSawValue;

        public StagePropertyBehavior(Action<bool> reportEndingSawValue)
        {
            this._reportEndingSawValue = reportEndingSawValue;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            if (context.Stage == WorkflowStage.Starting)
            {
                context.Properties["from-starting"] = "value";
            }
            else
            {
                this._reportEndingSawValue(context.Properties.ContainsKey("from-starting"));
            }

            return await continuation(cancellationToken);
        }
    }

    private sealed class PerInvocationPropertyBehavior : IExecutorBehavior
    {
        private readonly List<bool> _sawExistingValue;

        public PerInvocationPropertyBehavior(List<bool> sawExistingValue)
        {
            this._sawExistingValue = sawExistingValue;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._sawExistingValue.Add(context.Properties.ContainsKey("marker"));
            context.Properties["marker"] = "set";
            return await continuation(cancellationToken);
        }
    }

    private sealed class NamedWorkflowBehavior : IWorkflowBehavior
    {
        private readonly string _name;
        private readonly List<string> _log;

        public NamedWorkflowBehavior(string name, List<string> log)
        {
            this._name = name;
            this._log = log;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            this._log.Add($"{this._name}:{context.Stage}");
            return await continuation(cancellationToken);
        }
    }

    private sealed class FaultyEndingWorkflowBehavior : IWorkflowBehavior
    {
        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            if (context.Stage == WorkflowStage.Ending)
            {
                throw new InvalidOperationException("Ending behavior failed");
            }

            return await continuation(cancellationToken);
        }
    }

    private sealed class ValidationExecutorBehavior : IExecutorBehavior
    {
        private readonly List<string> _log;

        public ValidationExecutorBehavior(List<string> log)
        {
            this._log = log;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._log.Add($"Validation:{context.Stage}:{context.ExecutorId}");
            if (context.Message == null)
            {
                throw new InvalidOperationException("Message cannot be null");
            }
            return await continuation(cancellationToken);
        }
    }

    private sealed class PerformanceMonitoringBehavior : IExecutorBehavior
    {
        private readonly Dictionary<string, long> _measurements;

        public PerformanceMonitoringBehavior(Dictionary<string, long> measurements)
        {
            this._measurements = measurements;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            if (context.Stage == ExecutorStage.PreExecution)
            {
                var stopwatch = Stopwatch.StartNew();
                var result = await continuation(cancellationToken);
                stopwatch.Stop();
                this._measurements[context.ExecutorId] = stopwatch.ElapsedMilliseconds;
                return result;
            }

            return await continuation(cancellationToken);
        }
    }

    private sealed class ShortCircuitBehavior : IExecutorBehavior
    {
        private readonly object _result;

        public ShortCircuitBehavior(object result)
        {
            this._result = result;
        }

        public ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken) =>
            new ValueTask<object?>(this._result);
    }

    private sealed class FaultyBehavior : IExecutorBehavior
    {
        public ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken) =>
            throw new InvalidOperationException("Intentional behavior failure for testing");
    }

    private sealed class CapturingWorkflowBehavior : IWorkflowBehavior
    {
        private readonly Action<WorkflowBehaviorContext> _capture;

        public CapturingWorkflowBehavior(Action<WorkflowBehaviorContext> capture)
        {
            this._capture = capture;
        }

        public async ValueTask<TResult> HandleAsync<TResult>(
            WorkflowBehaviorContext context,
            WorkflowBehaviorContinuation<TResult> continuation,
            CancellationToken cancellationToken)
        {
            if (context.Stage == WorkflowStage.Starting)
            {
                this._capture(context);
            }

            return await continuation(cancellationToken);
        }
    }

    private sealed class CapturingExecutorBehavior : IExecutorBehavior
    {
        private readonly Action<ExecutorBehaviorContext> _capture;

        public CapturingExecutorBehavior(Action<ExecutorBehaviorContext> capture)
        {
            this._capture = capture;
        }

        public async ValueTask<object?> HandleAsync(
            ExecutorBehaviorContext context,
            ExecutorBehaviorContinuation continuation,
            CancellationToken cancellationToken)
        {
            this._capture(context);
            return await continuation(cancellationToken);
        }
    }
}
