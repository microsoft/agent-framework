// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
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
    private readonly WorkflowAgentOptions _options;
    private readonly ChatHistoryProvider? _chatHistoryProvider;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly Task<ProtocolDescriptor> _describeTask;

    private readonly ConcurrentDictionary<string, string> _assignedSessionIds = [];

    public WorkflowHostAgent(Workflow workflow, WorkflowAgentOptions? options = null)
    {
        this._workflow = Throw.IfNull(workflow);
        this._options = options?.Clone() ?? new();
        this._chatHistoryProvider = this._options.ChatHistoryProvider;

        this._executionEnvironment = this._options.ExecutionEnvironment ?? (workflow.AllowConcurrent
                                                                            ? InProcessExecution.Concurrent
                                                                            : InProcessExecution.OffThread);

        if (!this._executionEnvironment.IsCheckpointingEnabled &&
             this._executionEnvironment is not InProcessExecutionEnvironment)
        {
            // Cannot have an implicit CheckpointManager for non-InProcessExecution environments (or others that
            // support BYO Checkpointing.
            throw new InvalidOperationException("Cannot use a non-checkpointed execution environment. Implicit checkpointing is supported only for InProcess.");
        }

        // Kick off the typecheck right away by starting the DescribeProtocol task.
        this._describeTask = this._workflow.DescribeProtocolAsync().AsTask();
    }

    protected override string? IdCore => this._options.Id;
    public override string? Name => this._options.Name;
    public override string? Description => this._options.Description;

    /// <summary>
    /// Reports whether this agent was built with an execution environment that already names a
    /// checkpoint manager, meaning the caller chose where its checkpoints are written.
    /// </summary>
    internal bool UsesOwnCheckpointStorage => this._executionEnvironment.IsCheckpointingEnabled;

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        Throw.IfNull(serviceType);

        return base.GetService(serviceType, serviceKey)
            ?? (serviceKey is null && serviceType == typeof(WorkflowAgentMetadata)
                ? this._metadata ??= new WorkflowAgentMetadata(this.UsesOwnCheckpointStorage)
                : null)
            ?? this._chatHistoryProvider?.GetService(serviceType, serviceKey);
    }

    private WorkflowAgentMetadata? _metadata;

    /// <summary>
    /// Builds a copy of this agent that writes its checkpoints to <paramref name="checkpointManager"/>.
    /// Returns this same instance when the execution environment already names a checkpoint manager,
    /// because that means the caller made an explicit choice.
    /// </summary>
    internal AIAgent WithCheckpointing(CheckpointManager checkpointManager)
    {
        if (this._executionEnvironment.IsCheckpointingEnabled ||
            this._executionEnvironment is not InProcessExecutionEnvironment inProcEnvironment)
        {
            return this;
        }

        WorkflowAgentOptions options = this._options.Clone();
        options.ExecutionEnvironment = inProcEnvironment.WithCheckpointing(checkpointManager);

        return new WorkflowHostAgent(this._workflow, options);
    }

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
        => new(new WorkflowSession(this._workflow, this.GenerateNewId(), this._executionEnvironment, this._options.IncludeExceptionDetails, this._options.IncludeWorkflowOutputsInResponse));

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
        => new(new WorkflowSession(this._workflow, serializedState, this._executionEnvironment, this._options.IncludeExceptionDetails, this._options.IncludeWorkflowOutputsInResponse, jsonSerializerOptions));

    /// <summary>
    /// Resolves the <see cref="WorkflowSession"/> for this run and computes the messages to send to the workflow.
    /// </summary>
    /// <returns>
    /// The session, and the input messages for this run: the new messages when a custom <see cref="ChatHistoryProvider"/>
    /// is configured, otherwise the messages after the bookmark of the default provider. The input messages are sent
    /// to the workflow and then passed to the custom provider as request messages when the run completes or fails.
    /// </returns>
    private async ValueTask<(WorkflowSession Session, List<ChatMessage> InputMessages)> UpdateSessionAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, CancellationToken cancellationToken = default)
    {
        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        if (session is not WorkflowSession workflowSession)
        {
            throw new ArgumentException($"Incompatible session type: {session.GetType()} (expecting {typeof(WorkflowSession)})", nameof(session));
        }

        if (this._chatHistoryProvider is not null)
        {
            // The workflow keeps its own conversation state, so only the new messages are sent to it.
            return (workflowSession, messages.ToList());
        }

        workflowSession.ChatHistoryProvider.AddMessages(session, messages);
        return (workflowSession, workflowSession.ChatHistoryProvider.GetFromBookmark(workflowSession).ToList());
    }

    private async ValueTask StoreChatHistoryAsync(WorkflowSession workflowSession, List<ChatMessage> inputMessages, AgentResponse response, CancellationToken cancellationToken)
    {
        if (this._chatHistoryProvider is not null)
        {
            ChatHistoryProvider.InvokedContext context = new(this, workflowSession, inputMessages, response.Messages);
            await this._chatHistoryProvider.InvokedAsync(context, cancellationToken).ConfigureAwait(false);
            return;
        }

        workflowSession.ChatHistoryProvider.AddMessages(workflowSession, response.Messages);
        workflowSession.ChatHistoryProvider.UpdateBookmark(workflowSession);
    }

    private async IAsyncEnumerable<AgentResponseUpdate> InvokeStageAsync(
        WorkflowSession workflowSession,
        List<ChatMessage> inputMessages,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        IAsyncEnumerator<AgentResponseUpdate> enumerator = workflowSession.InvokeStageAsync(inputMessages, cancellationToken).GetAsyncEnumerator(cancellationToken);
        try
        {
            while (true)
            {
                try
                {
                    if (!await enumerator.MoveNextAsync().ConfigureAwait(false))
                    {
                        break;
                    }
                }
                catch (Exception ex) when (this._chatHistoryProvider is not null)
                {
                    ChatHistoryProvider.InvokedContext context = new(this, workflowSession, inputMessages, ex);
                    await this._chatHistoryProvider.InvokedAsync(context, cancellationToken).ConfigureAwait(false);
                    throw;
                }

                yield return enumerator.Current;
            }
        }
        finally
        {
            await enumerator.DisposeAsync().ConfigureAwait(false);
        }
    }

    protected override async
    Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        (WorkflowSession workflowSession, List<ChatMessage> inputMessages) = await this.UpdateSessionAsync(messages, session, cancellationToken).ConfigureAwait(false);
        ResponseMergeState mergeState = new();

        await foreach (AgentResponseUpdate update in this.InvokeStageAsync(workflowSession, inputMessages, cancellationToken)
                                                         .ConfigureAwait(false))
        {
            mergeState.AddUpdate(update, this.IsTerminalWorkflowOutputUpdate(update));
        }

        AgentResponse response = mergeState.ComputeMerged(workflowSession.LastResponseId!, this.Id, this.Name);
        await this.StoreChatHistoryAsync(workflowSession, inputMessages, response, cancellationToken).ConfigureAwait(false);

        return response;
    }

    protected override async
    IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await this.ValidateWorkflowAsync().ConfigureAwait(false);

        (WorkflowSession workflowSession, List<ChatMessage> inputMessages) = await this.UpdateSessionAsync(messages, session, cancellationToken).ConfigureAwait(false);
        ResponseMergeState mergeState = new();

        await foreach (AgentResponseUpdate update in this.InvokeStageAsync(workflowSession, inputMessages, cancellationToken)
                                                         .ConfigureAwait(false))
        {
            mergeState.AddUpdate(update, this.IsTerminalWorkflowOutputUpdate(update));
            yield return update;
        }

        AgentResponse response = mergeState.ComputeMerged(workflowSession.LastResponseId!, this.Id, this.Name);
        await this.StoreChatHistoryAsync(workflowSession, inputMessages, response, cancellationToken).ConfigureAwait(false);
    }

    private sealed class ResponseMergeState
    {
        private readonly MessageMerger _allUpdates = new();
        private readonly MessageMerger _terminalWorkflowOutputs = new();
        private bool _hasTerminalWorkflowOutputs;

        public void AddUpdate(AgentResponseUpdate update, bool isTerminalWorkflowOutput)
        {
            this._allUpdates.AddUpdate(update);
            if (isTerminalWorkflowOutput)
            {
                this._terminalWorkflowOutputs.AddUpdate(update);
                this._hasTerminalWorkflowOutputs = true;
            }
        }

        public AgentResponse ComputeMerged(string responseId, string? agentId, string? agentName)
        {
            MessageMerger merger = this._hasTerminalWorkflowOutputs
                ? this._terminalWorkflowOutputs
                : this._allUpdates;
            return merger.ComputeMerged(responseId, agentId, agentName);
        }
    }

    private bool IsTerminalWorkflowOutputUpdate(AgentResponseUpdate update)
    {
        if (update.RawRepresentation is not WorkflowOutputEvent output
            || output is AgentResponseUpdateEvent
            || output is AgentResponseEvent)
        {
            return false;
        }

        return this._workflow.IsTerminalOutput(output.ExecutorId);
    }
}
