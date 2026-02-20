// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowHostAgent : AIAgent
{
    private readonly Workflow _workflow;
    private readonly string? _id;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly bool _includeExceptionDetails;
    private readonly bool _includeWorkflowOutputsInResponse;
    private readonly Task<ProtocolDescriptor> _describeTask;

    private readonly ConcurrentDictionary<string, string> _assignedSessionIds = [];

    public WorkflowHostAgent(Workflow workflow, string? id = null, string? name = null, string? description = null, IWorkflowExecutionEnvironment? executionEnvironment = null, bool includeExceptionDetails = false, bool includeWorkflowOutputsInResponse = false)
    {
        this._workflow = Throw.IfNull(workflow);

        this._executionEnvironment = executionEnvironment ?? (workflow.AllowConcurrent
                                                              ? InProcessExecution.Concurrent
                                                              : InProcessExecution.OffThread);

        if (!this._executionEnvironment.IsCheckpointingEnabled &&
             this._executionEnvironment is not InProcessExecutionEnvironment)
        {
            // Cannot have an implicit CheckpointManager for non-InProcessExecution environments (or others that
            // support BYO Checkpointing.
            throw new InvalidOperationException("Cannot use a non-checkpointed execution environment. Implicit checkpointing is supported only for InProcess.");
        }

        this._includeExceptionDetails = includeExceptionDetails;
        this._includeWorkflowOutputsInResponse = includeWorkflowOutputsInResponse;

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
        } while (!this._assignedSessionIds.TryAdd(result, result));

        return result;
    }

    private async ValueTask ValidateWorkflowAsync()
    {
        ProtocolDescriptor protocol = await this._describeTask.ConfigureAwait(false);
        protocol.ThrowIfNotChatProtocol(allowCatchAll: true);
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        => new(new WorkflowSession(this._workflow, this.GenerateNewId(), this._executionEnvironment, this._includeExceptionDetails, this._includeWorkflowOutputsInResponse));

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(session);

        if (session is not WorkflowSession workflowSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(WorkflowSession)}' can be serialized by this agent.");
        }

        return new(workflowSession.Serialize(jsonSerializerOptions));
    }

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        => new(new WorkflowSession(this._workflow, serializedState, this._executionEnvironment, this._includeExceptionDetails, this._includeWorkflowOutputsInResponse, jsonSerializerOptions));

    private async ValueTask<WorkflowSession> UpdateSessionAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, CancellationToken cancellationToken = default)
    {
        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        if (session is not WorkflowSession workflowSession)
        {
            throw new ArgumentException($"Incompatible session type: {session.GetType()} (expecting {typeof(WorkflowSession)})", nameof(session));
        }

        // For workflow threads, messages are added directly via the internal AddMessages method
        // The MessageStore methods are used for agent invocation scenarios
        workflowSession.ChatHistoryProvider.AddMessages(session, messages);
        return workflowSession;
    }

    protected override async
    Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        WorkflowSession workflowSession = await this.UpdateSessionAsync(messages, session, cancellationToken).ConfigureAwait(false);
        MessageMerger merger = new();

        await foreach (AgentResponseUpdate update in workflowSession.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            merger.AddUpdate(update);
        }

        return merger.ComputeMerged(workflowSession.LastResponseId!, this.Id, this.Name);
    }

    protected override async
    IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        WorkflowSession workflowSession = await this.UpdateSessionAsync(messages, session, cancellationToken).ConfigureAwait(false);
        await foreach (AgentResponseUpdate update in workflowSession.InvokeStageAsync(cancellationToken)
                                                                      .ConfigureAwait(false)
                                                                      .WithCancellation(cancellationToken))
        {
            yield return update;
        }
    }
}
