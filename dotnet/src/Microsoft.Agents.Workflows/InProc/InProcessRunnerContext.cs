// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;
using Microsoft.Agents.Workflows.Specialized;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.InProc;

internal class InProcessRunnerContext<TExternalInput> : IRunnerContext
{
    private StepContext _nextStep = new();
    private readonly Dictionary<string, ExecutorProvider<Executor>> _executorProviders;
    private readonly Dictionary<string, Executor> _executors = new();
    private readonly Dictionary<string, ExternalRequest> _externalRequests = new();

    public InProcessRunnerContext(Workflow workflow, ILogger? logger = null)
    {
        this._executorProviders = Throw.IfNull(workflow).ExecutorProviders;
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

            if (executor is RequestInputExecutor requestInputExecutor)
            {
                requestInputExecutor.AttachRequestSink(this);
            }
        }

        return executor;
    }

    public ValueTask AddExternalMessageAsync([NotNull] object message)
    {
        Throw.IfNull(message);

        this._nextStep.MessagesFor(ExecutorIdentity.None).Add(message);
        return default;
    }

    public bool NextStepHasActions => this._nextStep.HasMessages;
    public bool HasUnservicedRequests => this._externalRequests.Count > 0;

    public StepContext Advance()
    {
        return Interlocked.Exchange(ref this._nextStep, new StepContext());
    }

    public ValueTask AddEventAsync(WorkflowEvent workflowEvent)
    {
        this.QueuedEvents.Add(workflowEvent);
        return default;
    }

    public ValueTask SendMessageAsync(string executorId, object message)
    {
        this._nextStep.MessagesFor(executorId).Add(message);
        return default;
    }

    public IWorkflowContext Bind(string executorId)
    {
        return new BoundContext(this, executorId);
    }

    public ValueTask PostAsync(ExternalRequest request)
    {
        this._externalRequests.Add(request.RequestId, request);
        return this.AddEventAsync(new RequestInfoEvent(request));
    }

    public bool CompleteRequest(string requestId) => this._externalRequests.Remove(requestId);

    public readonly List<WorkflowEvent> QueuedEvents = new();

    internal StateManager StateManager { get; } = new();

    private class BoundContext(InProcessRunnerContext<TExternalInput> RunnerContext, string ExecutorId) : IWorkflowContext
    {
        public ValueTask AddEventAsync(WorkflowEvent workflowEvent) => RunnerContext.AddEventAsync(workflowEvent);
        public ValueTask SendMessageAsync(object message) => RunnerContext.SendMessageAsync(ExecutorId, message);

        public ValueTask QueueStateUpdateAsync<T>(string key, T? value, string? scopeName = null)
            => RunnerContext.StateManager.WriteStateAsync(ExecutorId, scopeName, key, value);

        public ValueTask<T?> ReadStateAsync<T>(string key, string? scopeName = null)
            => RunnerContext.StateManager.ReadStateAsync<T>(ExecutorId, scopeName, key);
    }
}
