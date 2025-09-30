// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.InProc;

internal sealed class InProcessRunnerContext : IRunnerContext
{
    private int _runEnded;
    private readonly string _runId;
    private readonly Workflow _workflow;

    private readonly EdgeMap _edgeMap;
    private readonly OutputFilter _outputFilter;

    private StepContext _nextStep = new();

    private readonly ConcurrentDictionary<string, Task<Executor>> _executors = new();
    private readonly ConcurrentQueue<Func<ValueTask>> _queuedExternalDeliveries = new();

    private readonly Dictionary<string, ExternalRequest> _externalRequests = [];

    public InProcessRunnerContext(Workflow workflow, string runId, IStepTracer? stepTracer, ILogger? logger = null)
    {
        workflow.TakeOwnership(this);
        this._workflow = workflow;
        this._runId = runId;

        this._edgeMap = new(this, this._workflow, stepTracer);
        this._outputFilter = new(workflow);
    }

    public async ValueTask<Executor> EnsureExecutorAsync(string executorId, IStepTracer? tracer)
    {
        this.CheckEnded();
        Task<Executor> executorTask = this._executors.GetOrAdd(executorId, CreateExecutorAsync);

        async Task<Executor> CreateExecutorAsync(string id)
        {
            if (!this._workflow.Registrations.TryGetValue(executorId, out var registration))
            {
                throw new InvalidOperationException($"Executor with ID '{executorId}' is not registered.");
            }

            Executor executor = await registration.ProviderAsync().ConfigureAwait(false);
            tracer?.TraceActivated(executorId);

            if (executor is RequestInfoExecutor requestInputExecutor)
            {
                requestInputExecutor.AttachRequestSink(this);
            }

            return executor;
        }

        return await executorTask.ConfigureAwait(false);
    }

    public ValueTask AddExternalMessageAsync(object message, Type declaredType)
    {
        this.CheckEnded();
        Throw.IfNull(message);

        this._queuedExternalDeliveries.Enqueue(PrepareExternalDeliveryAsync);
        return default;

        async ValueTask PrepareExternalDeliveryAsync()
        {
            DeliveryMapping? maybeMapping =
                await this._edgeMap.PrepareDeliveryForInputAsync(new(message, ExecutorIdentity.None, declaredType))
                                   .ConfigureAwait(false);

            maybeMapping?.MapInto(this._nextStep);
        }
    }

    public ValueTask AddExternalResponseAsync(ExternalResponse response)
    {
        this.CheckEnded();
        Throw.IfNull(response);

        this._queuedExternalDeliveries.Enqueue(PrepareExternalDeliveryAsync);
        return default;

        async ValueTask PrepareExternalDeliveryAsync()
        {
            if (!this.CompleteRequest(response.RequestId))
            {
                throw new InvalidOperationException($"No pending request with ID {response.RequestId} found in the workflow context.");
            }

            DeliveryMapping? maybeMapping =
                await this._edgeMap.PrepareDeliveryForResponseAsync(response)
                                   .ConfigureAwait(false);

            maybeMapping?.MapInto(this._nextStep);
        }
    }

    public bool NextStepHasActions => this._nextStep.HasMessages || !this._queuedExternalDeliveries.IsEmpty;
    public bool HasUnservicedRequests => this._externalRequests.Count > 0;

    public async ValueTask<StepContext> AdvanceAsync()
    {
        this.CheckEnded();

        while (this._queuedExternalDeliveries.TryDequeue(out var deliveryPrep))
        {
            // It's important we do not try to run these in parallel, because they make be modifying
            // inner edge state, etc.
            await deliveryPrep().ConfigureAwait(false);
        }

        return Interlocked.Exchange(ref this._nextStep, new StepContext());
    }

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
    {
        this.CheckEnded();
        this.QueuedEvents.Add(workflowEvent);
        return default;
    }

    public async ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null)
    {
        this.CheckEnded();
        MessageEnvelope envelope = new(message, sourceId, targetId: targetId);

        if (this._workflow.Edges.TryGetValue(sourceId, out HashSet<Edge>? edges))
        {
            foreach (Edge edge in edges)
            {
                DeliveryMapping? maybeMapping =
                    await this._edgeMap.PrepareDeliveryForEdgeAsync(edge, envelope)
                                       .ConfigureAwait(false);

                maybeMapping?.MapInto(this._nextStep);
            }
        }
    }

    public IWorkflowContext Bind(string executorId)
    {
        this.CheckEnded();
        return new BoundContext(this, executorId, this._outputFilter);
    }

    public ValueTask PostAsync(ExternalRequest request)
    {
        this.CheckEnded();
        this._externalRequests.Add(request.RequestId, request);
        return this.AddEventAsync(new RequestInfoEvent(request));
    }

    public bool CompleteRequest(string requestId)
    {
        this.CheckEnded();
        return this._externalRequests.Remove(requestId);
    }

    public readonly List<WorkflowEvent> QueuedEvents = [];

    internal StateManager StateManager { get; } = new();

    private sealed class BoundContext(InProcessRunnerContext RunnerContext, string ExecutorId, OutputFilter outputFilter) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => RunnerContext.AddEventAsync(workflowEvent);
        public ValueTask SendMessageAsync(object message, string? targetId = null) => RunnerContext.SendMessageAsync(ExecutorId, message, targetId);

        public async ValueTask YieldOutputAsync(object output)
        {
            RunnerContext.CheckEnded();
            Throw.IfNull(output);

            Executor sourceExecutor = await RunnerContext.EnsureExecutorAsync(ExecutorId, tracer: null).ConfigureAwait(false);
            if (!sourceExecutor.CanOutput(output.GetType()))
            {
                throw new InvalidOperationException($"Cannot output object of type {output.GetType().Name}. Expecting one of [{string.Join(", ", sourceExecutor.OutputTypes)}].");
            }

            if (outputFilter.CanOutput(ExecutorId, output))
            {
                await this.AddEventAsync(new WorkflowOutputEvent(output, ExecutorId)).ConfigureAwait(false);
            }
        }

        public ValueTask RequestHaltAsync() => this.AddEventAsync(new RequestHaltEvent());

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null)
            => RunnerContext.StateManager.ReadStateAsync<T>(ExecutorId, scopeName, key);

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null)
            => RunnerContext.StateManager.ReadKeysAsync(ExecutorId, scopeName);

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
            => RunnerContext.StateManager.WriteStateAsync(ExecutorId, scopeName, key, value);

        public ValueTask QueueClearScopeAsync(string? scopeName = null)
            => RunnerContext.StateManager.ClearStateAsync(ExecutorId, scopeName);
    }

    internal Task PrepareForCheckpointAsync(CancellationToken cancellationToken = default)
    {
        this.CheckEnded();

        return Task.WhenAll(this._executors.Values.Select(InvokeCheckpointingAsync));

        async Task InvokeCheckpointingAsync(Task<Executor> executorTask)
        {
            Executor executor = await executorTask.ConfigureAwait(false);
            await executor.OnCheckpointingAsync(this.Bind(executor.Id), cancellationToken).ConfigureAwait(false);
        }
    }

    internal Task NotifyCheckpointLoadedAsync(CancellationToken cancellationToken = default)
    {
        this.CheckEnded();

        return Task.WhenAll(this._executors.Values.Select(InvokeCheckpointRestoredAsync));

        async Task InvokeCheckpointRestoredAsync(Task<Executor> executorTask)
        {
            Executor executor = await executorTask.ConfigureAwait(false);
            await executor.OnCheckpointRestoredAsync(this.Bind(executor.Id), cancellationToken).ConfigureAwait(false);
        }
    }

    internal ValueTask<RunnerStateData> ExportStateAsync()
    {
        this.CheckEnded();

        if (this.QueuedEvents.Count > 0)
        {
            throw new InvalidOperationException("Cannot export state when there are queued events. Please process or clear the events before exporting state.");
        }

        Dictionary<string, List<PortableMessageEnvelope>> queuedMessages = this._nextStep.ExportMessages();
        RunnerStateData result = new(instantiatedExecutors: [.. this._executors.Keys],
                                     queuedMessages,
                                     outstandingRequests: [.. this._externalRequests.Values]);

        return new(result);
    }

    internal async ValueTask RepublishUnservicedRequestsAsync(CancellationToken cancellationToken = default)
    {
        this.CheckEnded();

        if (this.HasUnservicedRequests)
        {
            foreach (string requestId in this._externalRequests.Keys)
            {
                await this.AddEventAsync(new RequestInfoEvent(this._externalRequests[requestId]))
                          .ConfigureAwait(false);
            }
        }
    }

    internal async ValueTask ImportStateAsync(Checkpoint checkpoint)
    {
        this.CheckEnded();

        if (this.QueuedEvents.Count > 0)
        {
            throw new InvalidOperationException("Cannot import state when there are queued events. Please process or clear the events before importing state.");
        }

        RunnerStateData importedState = checkpoint.RunnerData;

        Task<Executor>[] executorTasks = importedState.InstantiatedExecutors
                                                      .Where(id => !this._executors.ContainsKey(id))
                                                      .Select(id => this.EnsureExecutorAsync(id, tracer: null).AsTask())
                                                      .ToArray();

        this._nextStep = new StepContext();
        this._nextStep.ImportMessages(importedState.QueuedMessages);

        this._externalRequests.Clear();

        foreach (ExternalRequest request in importedState.OutstandingRequests)
        {
            // TODO: Reduce the amount of data we need to store in the checkpoint by not storing the entire request object.
            // For example, the Port object is not needed - we should be able to reconstruct it from the ID and the workflow
            // definition.
            this._externalRequests[request.RequestId] = request;
        }

        await Task.WhenAll(executorTasks).ConfigureAwait(false);
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
        Justification = "Does not exist in NetFx 4.7.2")]
    internal void CheckEnded()
    {
        if (Volatile.Read(ref this._runEnded) == 1)
        {
            throw new InvalidOperationException($"Workflow run '{this._runId}' has been ended. Please start a new Run or StreamingRun.");
        }
    }

    public async ValueTask EndRunAsync()
    {
        if (Interlocked.Exchange(ref this._runEnded, 1) == 0)
        {
            await this._workflow.ReleaseOwnershipAsync(this).ConfigureAwait(false);
        }
    }
}
