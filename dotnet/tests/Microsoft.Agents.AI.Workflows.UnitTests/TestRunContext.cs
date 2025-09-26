// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
            => runnerContext.AddEventAsync(workflowEvent);

        public ValueTask YieldOutputAsync(object output)
            => this.AddEventAsync(new WorkflowOutputEvent(output, executorId));

        public ValueTask RequestHaltAsync()
            => this.AddEventAsync(new RequestHaltEvent());

        public ValueTask QueueClearScopeAsync(string? scopeName = null)
            => default;

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
            => default;

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null)
            => new(default(T?));

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null)
            => new([]);

        public ValueTask SendMessageAsync(object message, string? targetId = null)
            => runnerContext.SendMessageAsync(executorId, message, targetId);

        public IReadOnlyDictionary<string, string>? TraceContext => traceContext;
    }

    public List<WorkflowEvent> Events { get; } = [];

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
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
    public ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null)
    {
        if (!this.QueuedMessages.TryGetValue(sourceId, out List<MessageEnvelope>? deliveryQueue))
        {
            this.QueuedMessages[sourceId] = deliveryQueue = [];
        }

        deliveryQueue.Add(new(message, sourceId, targetId: targetId));
        return default;
    }

    ValueTask<StepContext> IRunnerContext.AdvanceAsync() =>
        throw new NotImplementedException();

    public Dictionary<string, Executor> Executors { get; set; } = [];
    public string StartingExecutorId { get; set; } = string.Empty;

    public bool WithCheckpointing => throw new NotSupportedException();

    ValueTask<Executor> IRunnerContext.EnsureExecutorAsync(string executorId, IStepTracer? tracer) =>
        new(this.Executors[executorId]);

    public ValueTask<IEnumerable<Type>> GetStartingExecutorInputTypesAsync(CancellationToken cancellation = default)
    {
        if (this.Executors.TryGetValue(this.StartingExecutorId, out Executor? executor))
        {
            return new(executor.InputTypes);
        }

        throw new InvalidOperationException($"No executor with ID '{this.StartingExecutorId}' is registered in this context.");
    }

    public ValueTask ForwardWorkflowEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellation = default)
        => this.AddEventAsync(workflowEvent);

    public ValueTask SendMessageAsync<TMessage>(string senderId, [DisallowNull] TMessage message, CancellationToken cancellation = default)
        => this.SendMessageAsync(senderId, message, cancellation);

    ValueTask ISuperStepJoinContext.AttachSuperstepAsync(ISuperStepRunner superStepRunner, CancellationToken cancellation) => default;
}
