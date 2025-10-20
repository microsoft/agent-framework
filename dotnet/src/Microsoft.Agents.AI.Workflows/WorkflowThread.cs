// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowThread : AgentThread
{
    private readonly Workflow _workflow;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;

    private readonly CheckpointManager _checkpointManager;
    private readonly InMemoryCheckpointManager? _inMemoryCheckpointManager;

    public WorkflowThread(Workflow workflow, string runId, IWorkflowExecutionEnvironment executionEnvironment, CheckpointManager? checkpointManager = null)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);

        // If the user provided an external checkpoint manager, use that, otherwise rely on an in-memory one.
        // TODO: Implement persist-only-last functionality for in-memory checkpoint manager, to avoid unbounded
        // memory growth.
        this._checkpointManager = checkpointManager ?? new(this._inMemoryCheckpointManager = new());

        this.RunId = Throw.IfNullOrEmpty(runId);
        this.MessageStore = new WorkflowMessageStore();
    }

    public WorkflowThread(Workflow workflow, JsonElement serializedThread, IWorkflowExecutionEnvironment executionEnvironment, CheckpointManager? checkpointManager = null, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);

        JsonMarshaller marshaller = new(jsonSerializerOptions);
        ThreadState threadState = marshaller.Marshal<ThreadState>(serializedThread);

        this._inMemoryCheckpointManager = threadState.CheckpointManager;
        if (this._inMemoryCheckpointManager is not null && checkpointManager is not null)
        {
            // The thread was externalized with an in-memory checkpoint manager, but the caller is providing an external one.
            throw new ArgumentException("Cannot provide an external checkpoint manager when deserializing a thread that " +
                "was serialized with an in-memory checkpoint manager.", nameof(checkpointManager));
        }
        else if (this._inMemoryCheckpointManager is null && checkpointManager is null)
        {
            // The thread was externalized without an in-memory checkpoint manager, and the caller is not providing an external one.
            throw new ArgumentException("An external checkpoint manager must be provided when deserializing a thread that " +
                "was serialized without an in-memory checkpoint manager.", nameof(checkpointManager));
        }
        else
        {
            this._checkpointManager = checkpointManager ?? new(this._inMemoryCheckpointManager!);
        }

        this.RunId = threadState.RunId;
        this.LastCheckpoint = threadState.LastCheckpoint;
        this.MessageStore = new WorkflowMessageStore(threadState.MessageStoreState);
    }

    public CheckpointInfo? LastCheckpoint { get; set; }

    protected override Task MessagesReceivedAsync(IEnumerable<ChatMessage> newMessages, CancellationToken cancellationToken = default)
        => this.MessageStore.AddMessagesAsync(newMessages, cancellationToken);

    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonMarshaller marshaller = new(jsonSerializerOptions);
        ThreadState info = new(
            this.RunId,
            this.LastCheckpoint,
            this.MessageStore.ExportStoreState(),
            this._inMemoryCheckpointManager);

        return marshaller.Marshal(info);
    }

    public AgentRunResponseUpdate CreateUpdate(string responseId, params AIContent[] parts)
    {
        Throw.IfNullOrEmpty(parts);

        AgentRunResponseUpdate update = new(ChatRole.Assistant, parts)
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
            Role = ChatRole.Assistant,
            ResponseId = responseId
        };

        this.MessageStore.AddMessages(update.ToChatMessage());

        return update;
    }

    private async ValueTask<Checkpointed<StreamingRun>> CreateOrResumeRunAsync(List<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        if (this.LastCheckpoint is not null)
        {
            Checkpointed<StreamingRun> checkpointed =
                await this._executionEnvironment
                            .ResumeStreamAsync(this._workflow,
                                               this.LastCheckpoint,
                                               this._checkpointManager,
                                               this.RunId,
                                               cancellationToken)
                            .ConfigureAwait(false);

            await checkpointed.Run.TrySendMessageAsync(messages).ConfigureAwait(false);
            return checkpointed;
        }

        return await this._executionEnvironment
                            .StreamAsync(this._workflow,
                                         messages,
                                         this._checkpointManager,
                                         this.RunId,
                                         cancellationToken)
                            .ConfigureAwait(false);
    }

    internal async
    IAsyncEnumerable<AgentRunResponseUpdate> InvokeStageAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        try
        {
            this.LastResponseId = Guid.NewGuid().ToString("N");
            List<ChatMessage> messages = this.MessageStore.GetFromBookmark().ToList();

#pragma warning disable CA2007 // Analyzer misfiring and not seeing .ConfigureAwait(false) below.
            await using Checkpointed<StreamingRun> checkpointed =
                await this.CreateOrResumeRunAsync(messages, cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2007

            StreamingRun run = checkpointed.Run;
            await run.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
            await foreach (WorkflowEvent evt in run.WatchStreamAsync(blockOnPendingRequest: false, cancellationToken)
                                               .ConfigureAwait(false)
                                               .WithCancellation(cancellationToken))
            {
                switch (evt)
                {
                    case AgentRunUpdateEvent agentUpdate:
                        yield return agentUpdate.Update;
                        break;
                    case RequestInfoEvent requestInfo:
                        FunctionCallContent fcContent = requestInfo.Request.ToFunctionCall();
                        AgentRunResponseUpdate update = this.CreateUpdate(this.LastResponseId, fcContent);
                        yield return update;
                        break;
                    case SuperStepCompletedEvent stepCompleted:
                        this.LastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
                        break;
                }
            }
        }
        finally
        {
            // Do we want to try to undo the step, and not update the bookmark?
            this.MessageStore.UpdateBookmark();
        }
    }

    public string? LastResponseId { get; set; }

    public string RunId { get; }

    /// <inheritdoc/>
    public WorkflowMessageStore MessageStore { get; }

    internal sealed class ThreadState(
        string runId,
        CheckpointInfo? lastCheckpoint,
        WorkflowMessageStore.StoreState messageStoreState,
        InMemoryCheckpointManager? checkpointManager = null)
    {
        public string RunId { get; } = runId;
        public CheckpointInfo? LastCheckpoint { get; } = lastCheckpoint;
        public WorkflowMessageStore.StoreState MessageStoreState { get; } = messageStoreState;
        public InMemoryCheckpointManager? CheckpointManager { get; } = checkpointManager;
    }
}
