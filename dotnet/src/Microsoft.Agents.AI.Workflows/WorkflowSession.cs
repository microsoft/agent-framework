// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowSession : AgentSession
{
    private readonly Workflow _workflow;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly bool _includeExceptionDetails;
    private readonly bool _includeWorkflowOutputsInResponse;

    private readonly CheckpointManager _checkpointManager;
    private readonly InMemoryCheckpointManager? _inMemoryCheckpointManager;

    public WorkflowSession(Workflow workflow, string runId, IWorkflowExecutionEnvironment executionEnvironment, CheckpointManager? checkpointManager = null, bool includeExceptionDetails = false, bool includeWorkflowOutputsInResponse = false)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);
        this._includeExceptionDetails = includeExceptionDetails;
        this._includeWorkflowOutputsInResponse = includeWorkflowOutputsInResponse;

        // If the user provided an external checkpoint manager, use that, otherwise rely on an in-memory one.
        // TODO: Implement persist-only-last functionality for in-memory checkpoint manager, to avoid unbounded
        // memory growth.
        this._checkpointManager = checkpointManager ?? new(this._inMemoryCheckpointManager = new());

        this.RunId = Throw.IfNullOrEmpty(runId);
        this.ChatHistoryProvider = new WorkflowChatHistoryProvider();
    }

    public WorkflowSession(Workflow workflow, JsonElement serializedSession, IWorkflowExecutionEnvironment executionEnvironment, CheckpointManager? checkpointManager = null, bool includeExceptionDetails = false, bool includeWorkflowOutputsInResponse = false, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);
        this._includeExceptionDetails = includeExceptionDetails;
        this._includeWorkflowOutputsInResponse = includeWorkflowOutputsInResponse;

        JsonMarshaller marshaller = new(jsonSerializerOptions);
        SessionState sessionState = marshaller.Marshal<SessionState>(serializedSession);

        this._inMemoryCheckpointManager = sessionState.CheckpointManager;
        if (this._inMemoryCheckpointManager is not null && checkpointManager is not null)
        {
            // The session was externalized with an in-memory checkpoint manager, but the caller is providing an external one.
            throw new ArgumentException("Cannot provide an external checkpoint manager when deserializing a session that " +
                "was serialized with an in-memory checkpoint manager.", nameof(checkpointManager));
        }
        else if (this._inMemoryCheckpointManager is null && checkpointManager is null)
        {
            // The session was externalized without an in-memory checkpoint manager, and the caller is not providing an external one.
            throw new ArgumentException("An external checkpoint manager must be provided when deserializing a session that " +
                "was serialized without an in-memory checkpoint manager.", nameof(checkpointManager));
        }
        else
        {
            this._checkpointManager = checkpointManager ?? new(this._inMemoryCheckpointManager!);
        }

        this.RunId = sessionState.RunId;
        this.LastCheckpoint = sessionState.LastCheckpoint;
        this.ChatHistoryProvider = new WorkflowChatHistoryProvider(sessionState.ChatHistoryProviderState);
    }

    public CheckpointInfo? LastCheckpoint { get; set; }

    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonMarshaller marshaller = new(jsonSerializerOptions);
        SessionState info = new(
            this.RunId,
            this.LastCheckpoint,
            this.ChatHistoryProvider.ExportStoreState(),
            this._inMemoryCheckpointManager);

        return marshaller.Marshal(info);
    }

    public AgentResponseUpdate CreateUpdate(string responseId, object raw, params AIContent[] parts)
    {
        Throw.IfNullOrEmpty(parts);

        AgentResponseUpdate update = new(ChatRole.Assistant, parts)
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            RawRepresentation = raw
        };

        this.ChatHistoryProvider.AddMessages(update.ToChatMessage());

        return update;
    }

    public AgentResponseUpdate CreateUpdate(string responseId, object raw, ChatMessage message)
    {
        Throw.IfNull(message);

        AgentResponseUpdate update = new(message.Role, message.Contents)
        {
            CreatedAt = message.CreatedAt ?? DateTimeOffset.UtcNow,
            MessageId = message.MessageId ?? Guid.NewGuid().ToString("N"),
            ResponseId = responseId,
            RawRepresentation = raw
        };

        this.ChatHistoryProvider.AddMessages(update.ToChatMessage());

        return update;
    }

    private async ValueTask<Checkpointed<StreamingRun>> CreateOrResumeRunAsync(List<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        // The workflow is validated to be a ChatProtocol workflow by the WorkflowHostAgent before creating the session,
        // and does not need to be checked again here.
        if (this.LastCheckpoint is not null)
        {
            Checkpointed<StreamingRun> checkpointed =
                await this._executionEnvironment
                            .ResumeStreamAsync(this._workflow,
                                               this.LastCheckpoint,
                                               this._checkpointManager,
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
    IAsyncEnumerable<AgentResponseUpdate> InvokeStageAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        try
        {
            this.LastResponseId = Guid.NewGuid().ToString("N");
            List<ChatMessage> messages = this.ChatHistoryProvider.GetFromBookmark().ToList();

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
                    case AgentResponseUpdateEvent agentUpdate:
                        yield return agentUpdate.Update;
                        break;

                    case RequestInfoEvent requestInfo:
                        FunctionCallContent fcContent = requestInfo.Request.ToFunctionCall();
                        AgentResponseUpdate update = this.CreateUpdate(this.LastResponseId, evt, fcContent);
                        yield return update;
                        break;

                    case WorkflowErrorEvent workflowError:
                        Exception? exception = workflowError.Exception;
                        if (exception is TargetInvocationException tie && tie.InnerException != null)
                        {
                            exception = tie.InnerException;
                        }

                        if (exception != null)
                        {
                            string message = this._includeExceptionDetails
                                           ? exception.Message
                                           : "An error occurred while executing the workflow.";

                            ErrorContent errorContent = new(message);
                            yield return this.CreateUpdate(this.LastResponseId, evt, errorContent);
                        }

                        break;

                    case SuperStepCompletedEvent stepCompleted:
                        this.LastCheckpoint = stepCompleted.CompletionInfo?.Checkpoint;
                        goto default;

                    case WorkflowOutputEvent output:
                        IEnumerable<ChatMessage>? updateMessages = output.Data switch
                        {
                            IEnumerable<ChatMessage> chatMessages => chatMessages,
                            ChatMessage chatMessage => [chatMessage],
                            _ => null
                        };

                        if (!this._includeWorkflowOutputsInResponse || updateMessages == null)
                        {
                            goto default;
                        }

                        foreach (ChatMessage message in updateMessages)
                        {
                            yield return this.CreateUpdate(this.LastResponseId, evt, message);
                        }
                        break;

                    default:
                        // Emit all other workflow events for observability (DevUI, logging, etc.)
                        yield return new AgentResponseUpdate(ChatRole.Assistant, [])
                        {
                            CreatedAt = DateTimeOffset.UtcNow,
                            MessageId = Guid.NewGuid().ToString("N"),
                            Role = ChatRole.Assistant,
                            ResponseId = this.LastResponseId,
                            RawRepresentation = evt
                        };
                        break;
                }
            }
        }
        finally
        {
            // Do we want to try to undo the step, and not update the bookmark?
            this.ChatHistoryProvider.UpdateBookmark();
        }
    }

    public string? LastResponseId { get; set; }

    public string RunId { get; }

    /// <inheritdoc/>
    public WorkflowChatHistoryProvider ChatHistoryProvider { get; }

    internal sealed class SessionState(
        string runId,
        CheckpointInfo? lastCheckpoint,
        WorkflowChatHistoryProvider.StoreState chatHistoryProviderState,
        InMemoryCheckpointManager? checkpointManager = null)
    {
        public string RunId { get; } = runId;
        public CheckpointInfo? LastCheckpoint { get; } = lastCheckpoint;
        public WorkflowChatHistoryProvider.StoreState ChatHistoryProviderState { get; } = chatHistoryProviderState;
        public InMemoryCheckpointManager? CheckpointManager { get; } = checkpointManager;
    }
}
