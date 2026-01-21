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
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly bool _includeExceptionDetails;
    private readonly Task<ProtocolDescriptor> _describeTask;

    private readonly ConcurrentDictionary<string, string> _assignedRunIds = [];

    public WorkflowHostAgent(Workflow workflow, string? id = null, string? name = null, string? description = null, CheckpointManager? checkpointManager = null, IWorkflowExecutionEnvironment? executionEnvironment = null, bool includeExceptionDetails = false)
    {
        this._workflow = Throw.IfNull(workflow);

        this._executionEnvironment = executionEnvironment ?? (workflow.AllowConcurrent
                                                              ? InProcessExecution.Concurrent
                                                              : InProcessExecution.OffThread);
        this._checkpointManager = checkpointManager;
        this._includeExceptionDetails = includeExceptionDetails;

        this._id = id;
        this.Name = name;
        this.Description = description;

        // Kick off the typecheck right away by starting the DescribeProtocol task.
        this._describeTask = this._workflow.DescribeProtocolAsync().AsTask();
    }

    protected override string? IdCore => this._id;
    public override string? Name { get; }
    public override string? Description { get; }

    private string GenerateNewId()
    {
        string result;

        do
        {
            result = Guid.NewGuid().ToString("N");
        } while (!this._assignedRunIds.TryAdd(result, result));

        return result;
    }

    private async ValueTask ValidateWorkflowAsync()
    {
        ProtocolDescriptor protocol = await this._describeTask.ConfigureAwait(false);
        protocol.ThrowIfNotChatProtocol();
    }

    public override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken = default)
        => new(new WorkflowThread(this._workflow, this.GenerateNewId(), this._executionEnvironment, this._checkpointManager, this._includeExceptionDetails));

    public override ValueTask<AgentThread> DeserializeThreadAsync(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(new WorkflowThread(this._workflow, serializedThread, this._executionEnvironment, this._checkpointManager, this._includeExceptionDetails, jsonSerializerOptions));

    private async ValueTask<WorkflowThread> UpdateThreadAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, CancellationToken cancellationToken = default)
    {
        thread ??= await this.GetNewThreadAsync(cancellationToken).ConfigureAwait(false);

        if (thread is not WorkflowThread workflowThread)
        {
            throw new ArgumentException($"Incompatible thread type: {thread.GetType()} (expecting {typeof(WorkflowThread)})", nameof(thread));
        }

        // For workflow threads, messages are added directly via the internal AddMessages method
        // The MessageStore methods are used for agent invocation scenarios
        workflowThread.MessageStore.AddMessages(messages);
        return workflowThread;
    }

    protected override async
    Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        WorkflowThread workflowThread = await this.UpdateThreadAsync(messages, thread, cancellationToken).ConfigureAwait(false);
        MessageMerger merger = new();

        await foreach (AgentResponseUpdate update in workflowThread.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            merger.AddUpdate(update);
        }

        return merger.ComputeMerged(workflowThread.LastResponseId!, this.Id, this.Name);
    }

    protected override async
    IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        WorkflowThread workflowThread = await this.UpdateThreadAsync(messages, thread, cancellationToken).ConfigureAwait(false);
        await foreach (AgentResponseUpdate update in workflowThread.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            yield return update;
        }
    }
}
