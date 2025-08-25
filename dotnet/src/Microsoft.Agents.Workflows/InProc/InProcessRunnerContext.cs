// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

using Microsoft.Agents.Workflows.Execution;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.InProc;

internal class InProcessRunnerContext<TExternalInput> : IRunnerContext, IDisposable
{
    private readonly DataWaiter _nextStepWaiter = new();
    private StepContext _nextStep = new();
    private readonly Dictionary<string, ExecutorProvider<Executor>> _executorProviders;
    private readonly Dictionary<string, Executor> _executors = new();
    private readonly Dictionary<string, ExternalRequest> _externalRequests = new();

    public EventStream WorkflowEvents { get; } = new();
    public bool RaisedCompletion { get; private set; }

    public InProcessRunnerContext(Workflow workflow, ILogger? logger = null)
    {
        this._executorProviders = Throw.IfNull(workflow).ExecutorProviders;
    }

    public void Dispose()
    {
        this.WorkflowEvents.Dispose();
        this._nextStepWaiter.Dispose();
    }

    public async ValueTask<Executor> EnsureExecutorAsync(string executorId)
    {
        if (!this._executors.TryGetValue(executorId, out var executor))
        {
            if (!this._executorProviders.TryGetValue(executorId, out var provider))
            {
                throw new InvalidOperationException($"Executor with ID '{executorId}' is not registered.");
            }

            this._executors[executorId] = executor = provider();

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
        this._nextStepWaiter.Signal();

        return default;
    }

    public ValueTask AddExternalMessageAsync<T>(T message)
    {
        Throw.IfNull(message);

        this._nextStep.MessagesFor(ExecutorIdentity.None).Add(new MessageEnvelope(message, declaredType: typeof(T)));
        this._nextStepWaiter.Signal();

        return default;
    }

    public bool NextStepHasActions => this._nextStep.HasMessages;
    public bool HasUnservicedRequests => this._externalRequests.Count > 0;

    public async ValueTask JoinWaitUntilInputAsync(CancellationToken cancellation = default)
    {
        while (!cancellation.IsCancellationRequested && !this.NextStepHasActions)
        {
            await this._nextStepWaiter.JoinWaitForDataAsync(cancellation).ConfigureAwait(false);
        }
    }

    public StepContext Advance()
    {
        Console.WriteLine($"!!! Advancing step: hasMessages: {this._nextStep.HasMessages}");
        if (this._nextStep.HasMessages)
        {
            foreach (var kvp in this._nextStep.QueuedMessages)
            {
                string executorId = kvp.Key.Id ?? "<EXTERNAL>";
                Console.WriteLine($"!!! Executor '{executorId}' has {kvp.Value.Count} messages queued.");
            }
        }

        this._nextStepWaiter.Reset();
        return Interlocked.Exchange(ref this._nextStep, new StepContext());
    }

    private ValueTask RaiseEventAsync(WorkflowEvent workflowEvent)
    {
        this.WorkflowEvents.AddEvent(workflowEvent);
        if (workflowEvent is WorkflowCompletedEvent)
        {
            this.RaisedCompletion = true;
        }

        return default;
    }

    public ValueTask SendMessageAsync(string sourceId, object message, string? targetId = null)
    {
        this._nextStep.MessagesFor(sourceId).Add(new MessageEnvelope(message, targetId: targetId));
        this._nextStepWaiter.Signal();

        return default;
    }

    public IWorkflowContext Bind(string executorId)
    {
        return new BoundContext(this, executorId);
    }

    public ValueTask PostAsync(ExternalRequest request)
    {
        this._externalRequests.Add(request.RequestId, request);
        return this.RaiseEventAsync(new RequestInfoEvent(request));
    }

    public bool CompleteRequest(string requestId) => this._externalRequests.Remove(requestId);

    internal StateManager StateManager { get; } = new();

    private class BoundContext(InProcessRunnerContext<TExternalInput> RunnerContext, string ExecutorId) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => RunnerContext.RaiseEventAsync(workflowEvent);
        public ValueTask SendMessageAsync(object message, string? targetId = null) => RunnerContext.SendMessageAsync(ExecutorId, message, targetId);

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
            => RunnerContext.StateManager.WriteStateAsync(ExecutorId, scopeName, key, value);

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null)
            => RunnerContext.StateManager.ReadStateAsync<T>(ExecutorId, scopeName, key);
    }
}
