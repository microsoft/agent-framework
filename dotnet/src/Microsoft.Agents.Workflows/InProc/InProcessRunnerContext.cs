// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.Workflows.Checkpointing;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.InProc;

internal sealed class InProcessRunnerContext<TExternalInput> : IRunnerContext
{
    private StepContext _nextStep = new();
    private readonly Dictionary<string, ExecutorRegistration> _executorRegistrations;
    private readonly Dictionary<string, Executor> _executors = [];
    private readonly Dictionary<string, ExternalRequest> _externalRequests = [];

    public InProcessRunnerContext(Workflow workflow, ILogger? logger = null)
    {
        this._executorRegistrations = Throw.IfNull(workflow).Registrations;
    }

    public async ValueTask<Executor> EnsureExecutorAsync(string executorId, IStepTracer? tracer)
    {
        if (!this._executors.TryGetValue(executorId, out var executor))
        {
            if (!this._executorRegistrations.TryGetValue(executorId, out var registration))
            {
                throw new InvalidOperationException($"Executor with ID '{executorId}' is not registered.");
            }

            this._executors[executorId] = executor = await registration.ProviderAsync().ConfigureAwait(false);
            tracer?.TraceActivated(executorId);

            if (executor is RequestInfoExecutor requestInputExecutor)
            {
                requestInputExecutor.AttachRequestSink(this);
            }
        }

        return executor;
    }

    public ValueTask AddExternalMessageUntypedAsync(object message)
    {
        Throw.IfNull(message);

        this._nextStep.MessagesFor(ExecutorIdentity.None).Add(new MessageEnvelope(message));
        return default;
    }

    public ValueTask AddExternalMessageAsync<T>(T message)
    {
        Throw.IfNull(message);

        this._nextStep.MessagesFor(ExecutorIdentity.None).Add(new MessageEnvelope(message, declaredType: typeof(T)));
        return default;
    }

    public bool NextStepHasActions => this._nextStep.HasMessages;
    public bool HasUnservicedRequests => this._externalRequests.Count > 0;

    public StepContext Advance() => Interlocked.Exchange(ref this._nextStep, new StepContext());

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
    {
        this.QueuedEvents.Add(workflowEvent);
        return default;
    }

    public ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null)
    {
        this._nextStep.MessagesFor(sourceId).Add(new MessageEnvelope(message, targetId: targetId));
        return default;
    }

    public IWorkflowContext Bind(string executorId) => new BoundContext(this, executorId);

    public ValueTask PostAsync(ExternalRequest request)
    {
        this._externalRequests.Add(request.RequestId, request);
        return this.AddEventAsync(new RequestInfoEvent(request));
    }

    public bool CompleteRequest(string requestId) => this._externalRequests.Remove(requestId);

    public readonly List<WorkflowEvent> QueuedEvents = [];

    internal StateManager StateManager { get; } = new();

    private sealed class BoundContext(InProcessRunnerContext<TExternalInput> RunnerContext, string ExecutorId) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => RunnerContext.AddEventAsync(workflowEvent);
        public ValueTask SendMessageAsync(object message, string? targetId = null) => RunnerContext.SendMessageAsync(ExecutorId, message, targetId);

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null)
            => RunnerContext.StateManager.ReadStateAsync<T>(ExecutorId, scopeName, key);

        public ValueTask<HashSet<string>> ReadStateKeysAsync(string? scopeName = null)
            => RunnerContext.StateManager.ReadKeysAsync(ExecutorId, scopeName);

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
            => RunnerContext.StateManager.WriteStateAsync(ExecutorId, scopeName, key, value);

        public ValueTask QueueClearScopeAsync(string? scopeName = null)
            => RunnerContext.StateManager.ClearStateAsync(ExecutorId, scopeName);
    }

    internal Task PrepareForCheckpointAsync(CancellationToken cancellation = default) => Task.WhenAll(this._executors.Values.Select(executor => executor.OnCheckpointingAsync(this.Bind(executor.Id), cancellation).AsTask()));

    internal Task NotifyCheckpointLoadedAsync(CancellationToken cancellationToken = default) => Task.WhenAll(this._executors.Values.Select(executor => executor.OnCheckpointRestoredAsync(this.Bind(executor.Id), cancellationToken).AsTask()));

    internal ValueTask<RunnerStateData> ExportStateAsync()
    {
        if (this.QueuedEvents.Count > 0)
        {
            throw new InvalidOperationException("Cannot export state when there are queued events. Please process or clear the events before exporting state.");
        }

        Dictionary<ExecutorIdentity, List<PortableMessageEnvelope>> queuedMessages = this._nextStep.ExportMessages();
        RunnerStateData result = new(instantiatedExecutors: [.. this._executors.Keys],
                                     queuedMessages,
                                     outstandingRequests: [.. this._externalRequests.Values]);

        return new(result);
    }

    internal async ValueTask RepublishUnservicedRequestsAsync(CancellationToken cancellation = default)
    {
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
}
