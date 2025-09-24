// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

internal sealed class WorkflowHostAgent : AIAgent
{
    private readonly Workflow<List<ChatMessage>> _workflow;
    private readonly string? _id;

    private readonly ConcurrentDictionary<string, string> _assignedRunIds = [];
    private readonly Dictionary<string, StreamingRun> _runningWorkflows = [];

    public WorkflowHostAgent(Workflow<List<ChatMessage>> workflow, string? id = null, string? name = null)
    {
        this._workflow = Throw.IfNull(workflow, nameof(workflow));

        this._id = id;
        this.Name = name;
    }

    public override string? Name { get; }
    public override string Id => this._id ?? base.Id;

    private string GenerateNewId()
    {
        string result;

        do
        {
            result = Guid.NewGuid().ToString("N");
        } while (!this._assignedRunIds.TryAdd(result, result));

        return result;
    }

    public override AgentThread GetNewThread() => new WorkflowThread(this.Id, this.Name, this.GenerateNewId());

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new WorkflowThread(serializedThread, jsonSerializerOptions);

    private async
    IAsyncEnumerable<AgentRunResponseUpdate> InvokeStageAsync(
        WorkflowThread conversation,
        [EnumeratorCancellation] CancellationToken cancellation = default)
    {
        string runId = conversation.RunId;
        List<ChatMessage> messages = conversation.MessageStore.GetFromBookmark().ToList();

        try
        {
            // technically there is a race condition here between assigning the ID, and checking if it exists
            // in the case of new threads.
            if (!this._runningWorkflows.TryGetValue(runId, out StreamingRun? run))
            {
                run = await InProcessExecution.StreamAsync(this._workflow, messages, cancellation)
                                                       .ConfigureAwait(false);
                this._runningWorkflows[runId] = run;
            }
            else
            {
                bool sentMessages = await run.TrySendMessageAsync(messages).ConfigureAwait(false);
                Debug.Assert(sentMessages, "Hosted workflow is required to take List<ChatMessage> as input.");
            }

            await run.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
            await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false, cancellation)
                                               .ConfigureAwait(false)
                                               .WithCancellation(cancellation))
            {
                switch (evt)
                {
                    case AgentRunUpdateEvent agentUpdate:
                        yield return agentUpdate.Update;
                        break;
                    case RequestInfoEvent requestInfo:
                        FunctionCallContent fcContent = requestInfo.Request.ToFunctionCall();
                        AgentRunResponseUpdate update = conversation.CreateUpdate(fcContent);
                        yield return update;
                        break;
                }
            }
        }
        finally
        {
            // Do we want to try to undo the step, and not update the bookmark?
            conversation.MessageStore.UpdateBookmark();
        }
    }

    private async ValueTask<WorkflowThread> UpdateThreadAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, CancellationToken cancellation = default)
    {
        thread ??= this.GetNewThread();

        if (thread is not WorkflowThread workflowThread)
        {
            throw new ArgumentException($"Incompatible thread type: {thread.GetType()} (expecting {typeof(WorkflowThread)})", nameof(thread));
        }

        await workflowThread.MessageStore.AddMessagesAsync(messages, cancellation).ConfigureAwait(false);
        return workflowThread;
    }

    public override async
    Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        WorkflowThread workflowThread = await this.UpdateThreadAsync(messages, thread, cancellationToken).ConfigureAwait(false);
        MessageMerger merger = new();

        await foreach (AgentRunResponseUpdate update in this.InvokeStageAsync(workflowThread, cancellationToken)
                                                            .ConfigureAwait(false)
                                                            .WithCancellation(cancellationToken))
        {
            merger.AddUpdate(update);
        }

        return merger.ComputeMerged(workflowThread.ResponseId, this.Id, this.Name);
    }

    public override async
    IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        WorkflowThread workflowThread = await this.UpdateThreadAsync(messages, thread, cancellationToken).ConfigureAwait(false);
        await foreach (AgentRunResponseUpdate update in this.InvokeStageAsync(workflowThread, cancellationToken)
                                                            .ConfigureAwait(false)
                                                            .WithCancellation(cancellationToken))
        {
            yield return update;
        }
    }
}
