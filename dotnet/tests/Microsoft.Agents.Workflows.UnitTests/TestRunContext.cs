// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

public class TestRunContext : IRunnerContext
{
    private sealed class BoundContext(string executorId, TestRunContext runnerContext) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
            => runnerContext.AddEventAsync(workflowEvent);

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
    }

    public List<WorkflowEvent> Events { get; } = [];

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
    {
        this.Events.Add(workflowEvent);
        return default;
    }

    public IWorkflowContext Bind(string executorId) => new BoundContext(executorId, this);

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

        deliveryQueue.Add(new(message, targetId: targetId));
        return default;
    }

    StepContext IRunnerContext.Advance() =>
        throw new NotImplementedException();

    public Dictionary<string, Executor> Executors { get; } = [];

    ValueTask<Executor> IRunnerContext.EnsureExecutorAsync(string executorId, IStepTracer? tracer) =>
        new(this.Executors[executorId]);
}
