// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class TestRunContext : IRunnerContext
{
    private sealed class TestExternalRequestContext(IRunnerContext runnerContext, string executorId, EdgeMap? map) : IExternalRequestContext
    {
        public IExternalRequestSink RegisterPort(RequestPort port)
        {
            if (map?.TryRegisterPort(runnerContext, executorId, port) == false)
            {
                throw new InvalidOperationException("Duplicate port id: " + port.Id);
            }

            return runnerContext;
        }
    }

    internal TestRunContext ConfigureExecutor(Executor executor, EdgeMap? map = null)
    {
        executor.Configure(new TestExternalRequestContext(this, executor.Id, map));
        this.Executors.Add(executor.Id, executor);
        return this;
    }

    internal TestRunContext ConfigureExecutors(IEnumerable<Executor> executors, EdgeMap? map = null)
    {
        foreach (var executor in executors)
        {
            this.ConfigureExecutor(executor, map);
        }

        return this;
    }

    private sealed class BoundContext(
        string executorId,
        TestRunContext runnerContext,
        IReadOnlyDictionary<string, string>? traceContext) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent, CancellationToken cancellationToken = default)
            => runnerContext.AddEventAsync(workflowEvent, cancellationToken);

        public ValueTask YieldOutputAsync(object output, CancellationToken cancellationToken = default)
        {
            // Special-case AgentResponse and AgentResponseUpdate to create their specific event types
            // (consistent with InProcessRunnerContext.YieldOutputAsync)
            if (output is AgentResponseUpdate update)
            {
                return this.AddEventAsync(new AgentResponseUpdateEvent(executorId, update), cancellationToken);
            }
            else if (output is AgentResponse response)
            {
                return this.AddEventAsync(new AgentResponseEvent(executorId, response), cancellationToken);
            }

            return this.AddEventAsync(new WorkflowOutputEvent(output, executorId), cancellationToken);
        }

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

    public IWorkflowContext BindWorkflowContext(string executorId, Dictionary<string, string>? traceContext = null)
        => new BoundContext(executorId, this, traceContext);

    public ConcurrentQueue<ExternalRequest> ExternalRequests { get; } = [];
    public ValueTask PostAsync(ExternalRequest request)
    {
        this.ExternalRequests.Enqueue(request);
        return default;
    }

    internal Dictionary<string, List<MessageEnvelope>> QueuedMessages { get; } = [];

    internal Dictionary<string, List<object>> QueuedOutputs { get; } = [];

    public ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null, CancellationToken cancellationToken = default)
    {
        if (!this.QueuedMessages.TryGetValue(sourceId, out List<MessageEnvelope>? deliveryQueue))
        {
            this.QueuedMessages[sourceId] = deliveryQueue = [];
        }

        deliveryQueue.Add(new(message, sourceId, targetId: targetId));
        return default;
    }

    public ValueTask YieldOutputAsync(string sourceId, object output, CancellationToken cancellationToken = default)
    {
        if (!this.QueuedOutputs.TryGetValue(sourceId, out List<object>? outputQueue))
        {
            this.QueuedOutputs[sourceId] = outputQueue = [];
        }

        outputQueue.Add(output);
        return default;
    }

    ValueTask<StepContext> IRunnerContext.AdvanceAsync(CancellationToken cancellationToken) =>
        throw new NotImplementedException();

    public Dictionary<string, Executor> Executors { get; set; } = [];
    public string StartingExecutorId { get; set; } = string.Empty;

    public bool WithCheckpointing => false;
    public bool ConcurrentRunsEnabled => false;

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

    ValueTask ISuperStepJoinContext.SendMessageAsync<TMessage>(string senderId, [System.Diagnostics.CodeAnalysis.DisallowNull] TMessage message, CancellationToken cancellationToken)
        => this.SendMessageAsync(senderId, message, cancellationToken: cancellationToken);

    ValueTask ISuperStepJoinContext.YieldOutputAsync<TOutput>(string senderId, [System.Diagnostics.CodeAnalysis.DisallowNull] TOutput output, CancellationToken cancellationToken)
        => this.YieldOutputAsync(senderId, output, cancellationToken);

    ValueTask<string> ISuperStepJoinContext.AttachSuperstepAsync(ISuperStepRunner superStepRunner, CancellationToken cancellationToken) => new(string.Empty);
    ValueTask<bool> ISuperStepJoinContext.DetachSuperstepAsync(string joinId) => new(false);
}
