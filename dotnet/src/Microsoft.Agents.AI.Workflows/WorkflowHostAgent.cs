// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowHostAgent : AIAgent
{
    private readonly Workflow _workflow;
    private readonly string? _id;
    private readonly CheckpointManager? _checkpointManager;

    private readonly ConcurrentDictionary<string, string> _assignedRunIds = [];

    public WorkflowHostAgent(Workflow<List<ChatMessage>> workflow, string? id = null, string? name = null, CheckpointManager? checkpointManager = null)
    {
        this._workflow = Throw.IfNull(workflow);

        this._id = id;
        this.Name = name;
        this._checkpointManager = checkpointManager;
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

    public override AgentThread GetNewThread() => new WorkflowThread(this._workflow, this.GenerateNewId(), this._checkpointManager);

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new WorkflowThread(this._workflow, serializedThread, this._checkpointManager, jsonSerializerOptions);

    private async ValueTask<WorkflowThread> UpdateThreadAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, CancellationToken cancellationToken = default)
    {
        thread ??= this.GetNewThread();

        if (thread is not WorkflowThread workflowThread)
        {
            throw new ArgumentException($"Incompatible thread type: {thread.GetType()} (expecting {typeof(WorkflowThread)})", nameof(thread));
        }

        await workflowThread.MessageStore.AddMessagesAsync(messages, cancellationToken).ConfigureAwait(false);
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

        await foreach (AgentRunResponseUpdate update in workflowThread.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            merger.AddUpdate(update);
        }

        return merger.ComputeMerged(workflowThread.LastResponseId!, this.Id, this.Name);
    }

    public override async
    IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        WorkflowThread workflowThread = await this.UpdateThreadAsync(messages, thread, cancellationToken).ConfigureAwait(false);
        await foreach (AgentRunResponseUpdate update in workflowThread.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            yield return update;
        }
    }
}
