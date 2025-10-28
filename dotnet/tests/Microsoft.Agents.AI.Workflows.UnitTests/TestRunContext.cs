// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class TestRunContext : IRunnerContext
{
    private sealed class BoundContext(
        string executorId,
        TestRunContext runnerContext,
        IReadOnlyDictionary<string, string>? traceContext) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
            => runnerContext.AddEventAsync(workflowEvent, cancellationToken);

        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
            => this.AddEventAsync(new WorkflowOutputEvent(output, executorId), cancellationToken);

        public ValueTask RequestHaltAsync()
            => this.AddEventAsync(new RequestHaltEvent());

        public ValueTask QueueClearScopeAsync(string? scopeName = null, CancellationToken cancellationToken = default)
            => default;

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null, CancellationToken cancellationToken = default)
            => default;

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null, CancellationToken cancellationToken = default)
            => new(default(T?));

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null, CancellationToken cancellationToken = default)
            => new([]);

        public ValueTask SendMessageAsync(object message, string? targetId = null, CancellationToken cancellationToken = default)
            => runnerContext.SendMessageAsync(executorId, message, targetId, cancellationToken);

        public ValueTask<T> ReadOrInitStateAsync<T>(string key, Func<T> initialStateFactory, string? scopeName = null, CancellationToken cancellationToken = default)
        {
            return new(initialStateFactory());
        }

        public IReadOnlyDictionary<string, string>? TraceContext => traceContext;

        public bool ConcurrentRunsEnabled => runnerContext.ConcurrentRunsEnabled;
    }

    public List<WorkflowEvent> Events { get; } = [];

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken)
    {
        this.Events.Add(workflowEvent);
        return default;
    }

    public IWorkflowContext Bind(string executorId, Dictionary<string, string>? traceContext = null)
        => new BoundContext(executorId, this, traceContext);

    public List<ExternalRequest> ExternalRequests { get; } = [];
    public ValueTask PostAsync(ExternalRequest request)
    {
        this.ExternalRequests.Add(request);
        return default;
    }

    internal Dictionary<string, List<MessageEnvelope>> QueuedMessages { get; } = [];
    public ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null, CancellationToken cancellationToken = default)
    {
        if (!this.QueuedMessages.TryGetValue(sourceId, out List<MessageEnvelope>? deliveryQueue))
        {
            this.QueuedMessages[sourceId] = deliveryQueue = [];
        }

        deliveryQueue.Add(new(message, sourceId, targetId: targetId));
        return default;
    }

    ValueTask<StepContext> IRunnerContext.AdvanceAsync(CancellationToken cancellationToken) =>
        throw new NotImplementedException();

    public Dictionary<string, Executor> Executors { get; set; } = [];
    public string StartingExecutorId { get; set; } = string.Empty;

    public bool WithCheckpointing => throw new NotSupportedException();
    public bool ConcurrentRunsEnabled => throw new NotSupportedException();

    ValueTask<Executor> IRunnerContext.EnsureExecutorAsync(string executorId, IStepTracer? tracer, CancellationToken cancellationToken) =>
        new(this.Executors[executorId]);

    public ValueTask<IEnumerable<Type>> GetStartingExecutorInputTypesAsync(CancellationToken cancellationToken = default)
    {
        if (this.Executors.TryGetValue(this.StartingExecutorId, out Executor? executor))
        {
            return new(executor.InputTypes);
        }

        throw new InvalidOperationException($"No executor with ID '{this.StartingExecutorId}' is registered in this context.");
    }

    public ValueTask ForwardWorkflowEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
        => this.AddEventAsync(workflowEvent, cancellationToken);

    public ValueTask SendMessageAsync<TMessage>(string senderId, [System.Diagnostics.CodeAnalysis.DisallowNull] TMessage message, CancellationToken cancellationToken = default)
        => this.SendMessageAsync(senderId, message, cancellationToken);

    ValueTask<string> ISuperStepJoinContext.AttachSuperstepAsync(ISuperStepRunner superStepRunner, CancellationToken cancellationToken) => new(string.Empty);
    ValueTask<bool> ISuperStepJoinContext.DetachSuperstepAsync(string joinId) => new(false);
}
