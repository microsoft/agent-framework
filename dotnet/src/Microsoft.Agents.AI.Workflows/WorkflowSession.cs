// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.InProc;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class WorkflowSession : AgentSession
{
    private readonly Workflow _workflow;
    private readonly IWorkflowExecutionEnvironment _executionEnvironment;
    private readonly bool _includeExceptionDetails;
    private readonly bool _includeWorkflowOutputsInResponse;

    private InMemoryCheckpointManager? _inMemoryCheckpointManager;

    // Key prefix used in StateBag to track pending external requests by their content ID
    // This enables converting incoming response content back to ExternalResponse when resuming.
    private const string PendingRequestKeyPrefix = "workflow.pendingRequest:";

    internal static bool VerifyCheckpointingConfiguration(IWorkflowExecutionEnvironment executionEnvironment, [NotNullWhen(true)] out InProcessExecutionEnvironment? inProcEnv)
    {
        inProcEnv = null;
        if (executionEnvironment.IsCheckpointingEnabled)
        {
            return false;
        }

        if ((inProcEnv = executionEnvironment as InProcessExecutionEnvironment) == null)
        {
            throw new InvalidOperationException("Cannot use a non-checkpointed execution environment. Implicit checkpointing is supported only for InProcess.");
        }

        return true;
    }

    public WorkflowSession(Workflow workflow, string sessionId, IWorkflowExecutionEnvironment executionEnvironment, bool includeExceptionDetails = false, bool includeWorkflowOutputsInResponse = false)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);
        this._includeExceptionDetails = includeExceptionDetails;
        this._includeWorkflowOutputsInResponse = includeWorkflowOutputsInResponse;

        if (VerifyCheckpointingConfiguration(executionEnvironment, out InProcessExecutionEnvironment? inProcEnv))
        {
            // We have an InProcessExecutionEnvironment which is not configured for checkpointing. Ensure it has an externalizable checkpoint manager,
            // since we are responsible for maintaining the state.
            this._executionEnvironment = inProcEnv.WithCheckpointing(this.EnsureExternalizedInMemoryCheckpointing());
        }

        this.SessionId = Throw.IfNullOrEmpty(sessionId);
        this.ChatHistoryProvider = new WorkflowChatHistoryProvider();
    }

    private CheckpointManager EnsureExternalizedInMemoryCheckpointing()
    {
        return new(this._inMemoryCheckpointManager ??= new());
    }

    public WorkflowSession(Workflow workflow, JsonElement serializedSession, IWorkflowExecutionEnvironment executionEnvironment, bool includeExceptionDetails = false, bool includeWorkflowOutputsInResponse = false, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        this._workflow = Throw.IfNull(workflow);
        this._executionEnvironment = Throw.IfNull(executionEnvironment);
        this._includeExceptionDetails = includeExceptionDetails;
        this._includeWorkflowOutputsInResponse = includeWorkflowOutputsInResponse;

        JsonMarshaller marshaller = new(jsonSerializerOptions);
        SessionState sessionState = marshaller.Marshal<SessionState>(serializedSession);

        this._inMemoryCheckpointManager = sessionState.CheckpointManager;
        if (this._inMemoryCheckpointManager != null &&
            VerifyCheckpointingConfiguration(executionEnvironment, out InProcessExecutionEnvironment? inProcEnv))
        {
            this._executionEnvironment = inProcEnv.WithCheckpointing(this.EnsureExternalizedInMemoryCheckpointing());
        }
        else if (this._inMemoryCheckpointManager != null)
        {
            throw new ArgumentException("The session was saved with an externalized checkpoint manager, but the incoming execution environment does not support it.", nameof(executionEnvironment));
        }

        this.SessionId = sessionState.SessionId;
        this.ChatHistoryProvider = new WorkflowChatHistoryProvider();

        this.LastCheckpoint = sessionState.LastCheckpoint;
        this.StateBag = sessionState.StateBag;
    }

    public CheckpointInfo? LastCheckpoint { get; set; }

    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonMarshaller marshaller = new(jsonSerializerOptions);
        SessionState info = new(
            this.SessionId,
            this.LastCheckpoint,
            this._inMemoryCheckpointManager,
            this.StateBag);

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

        this.ChatHistoryProvider.AddMessages(this, update.ToChatMessage());

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

        this.ChatHistoryProvider.AddMessages(this, update.ToChatMessage());

        return update;
    }

    private async ValueTask<ResumeRunResult> CreateOrResumeRunAsync(List<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        // The workflow is validated to be a ChatProtocol workflow by the WorkflowHostAgent before creating the session,
        // and does not need to be checked again here.
        if (this.LastCheckpoint is not null)
        {
            StreamingRun run =
                await this._executionEnvironment
                            .ResumeStreamingAsync(this._workflow,
                                               this.LastCheckpoint,
                                               cancellationToken)
                            .ConfigureAwait(false);

            // Process messages: convert response content to ExternalResponse, send regular messages as-is
            bool hasMatchedExternalResponses = await this.SendMessagesWithResponseConversionAsync(run, messages).ConfigureAwait(false);
            return new ResumeRunResult(run, hasMatchedExternalResponses: hasMatchedExternalResponses);
        }

        StreamingRun newRun = await this._executionEnvironment
                            .RunStreamingAsync(this._workflow,
                                         messages,
                                         this.SessionId,
                                         cancellationToken)
                            .ConfigureAwait(false);
        return new ResumeRunResult(newRun);
    }

    /// <summary>
    /// Sends messages to the run, converting FunctionResultContent and UserInputResponseContent
    /// to ExternalResponse when there's a matching pending request.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> if any external responses were sent; otherwise, <see langword="false"/>.
    /// </returns>
    private async ValueTask<bool> SendMessagesWithResponseConversionAsync(StreamingRun run, List<ChatMessage> messages)
    {
        List<ChatMessage> regularMessages = [];
        // Responses are deferred until after regular messages are queued so response handlers
        // can merge buffered regular content in the same continuation turn.
        List<(ExternalResponse Response, string? ContentId)> externalResponses = [];
        bool hasMatchedExternalResponses = false;

        foreach (ChatMessage message in messages)
        {
            List<AIContent> regularContents = [];
            PartitionMessageContents(message, regularContents);

            if (regularContents.Count > 0)
            {
                ChatMessage cloned = message.Clone();
                cloned.Contents = regularContents;
                regularMessages.Add(cloned);
            }
        }

        // Send regular messages first so response handlers can merge them with responses.
        if (regularMessages.Count > 0)
        {
            await run.TrySendMessageAsync(regularMessages).ConfigureAwait(false);
        }

        // Send external responses after regular messages.
        foreach ((ExternalResponse response, string? contentId) in externalResponses)
        {
            await run.SendResponseAsync(response).ConfigureAwait(false);
            hasMatchedExternalResponses = true;

            if (contentId is string id)
            {
                this.RemovePendingRequest(id);
            }
        }

        return hasMatchedExternalResponses;

        void PartitionMessageContents(ChatMessage message, List<AIContent> regularContents)
        {
            foreach (AIContent content in message.Contents)
            {
                string? contentId = GetResponseContentId(content);
                if (this.TryCreateExternalResponse(content) is ExternalResponse response)
                {
                    externalResponses.Add((response, contentId));
                }
                else
                {
                    regularContents.Add(content);
                }
            }
        }
    }

    /// <summary>
    /// Attempts to create an ExternalResponse from response content (FunctionResultContent or UserInputResponseContent)
    /// by matching it to a pending request.
    /// </summary>
    private ExternalResponse? TryCreateExternalResponse(AIContent content)
    {
        string? contentId = GetResponseContentId(content);
        if (contentId == null)
        {
            return null;
        }

        ExternalRequest? pendingRequest = this.TryGetPendingRequest(contentId);
        if (pendingRequest == null)
        {
            return null;
        }

        // Create ExternalResponse via the pending request to ensure proper validation and wrapping
        return pendingRequest.CreateResponse(content);
    }

    /// <summary>
    /// Gets the content ID from response content types.
    /// </summary>
    private static string? GetResponseContentId(AIContent content) => content switch
    {
        FunctionResultContent functionResultContent => functionResultContent.CallId,
        UserInputResponseContent userInputResponseContent => userInputResponseContent.Id,
        _ => null
    };

    /// <summary>
    /// Tries to get a pending request from the state bag by content ID.
    /// </summary>
    private ExternalRequest? TryGetPendingRequest(string contentId) =>
        this.StateBag.GetValue<ExternalRequest>(PendingRequestKeyPrefix + contentId);

    /// <summary>
    /// Adds a pending request to the state bag.
    /// </summary>
    private void AddPendingRequest(string contentId, ExternalRequest request) =>
        this.StateBag.SetValue(PendingRequestKeyPrefix + contentId, request);

    /// <summary>
    /// Removes a pending request from the state bag.
    /// </summary>
    private void RemovePendingRequest(string contentId) =>
        this.StateBag.TryRemoveValue(PendingRequestKeyPrefix + contentId);

    internal async
    IAsyncEnumerable<AgentResponseUpdate> InvokeStageAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        try
        {
            this.LastResponseId = Guid.NewGuid().ToString("N");
            List<ChatMessage> messages = this.ChatHistoryProvider.GetFromBookmark(this).ToList();

            ResumeRunResult resumeResult =
                await this.CreateOrResumeRunAsync(messages, cancellationToken).ConfigureAwait(false);
#pragma warning disable CA2007 // Analyzer misfiring.
            await using StreamingRun run = resumeResult.Run;
#pragma warning restore CA2007

            // Send a TurnToken only when no external responses were delivered.
            // External response handlers already drive continuation turns and can merge
            // buffered regular messages, so an extra TurnToken would cause a redundant turn.
            if (!resumeResult.HasMatchedExternalResponses)
            {
                await run.TrySendMessageAsync(new TurnToken(emitEvents: true)).ConfigureAwait(false);
            }
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
                        (AIContent requestContent, string? contentId) = requestInfo.Request switch
                        {
                            ExternalRequest externalRequest when externalRequest.TryGetDataAs(out FunctionCallContent? fcc) => (fcc, fcc.CallId),
                            ExternalRequest externalRequest when externalRequest.TryGetDataAs(out UserInputRequestContent? uic) => (uic, uic.Id),
                            ExternalRequest externalRequest => ((AIContent)externalRequest.ToFunctionCall(), externalRequest.RequestId)
                        };

                        // Track the pending request so we can convert incoming responses back to ExternalResponse
                        if (contentId != null)
                        {
                            this.AddPendingRequest(contentId, requestInfo.Request);
                        }

                        AgentResponseUpdate update = this.CreateUpdate(this.LastResponseId, evt, requestContent);
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
            this.ChatHistoryProvider.UpdateBookmark(this);
        }
    }

    public string? LastResponseId { get; set; }

    public string SessionId { get; }

    /// <inheritdoc/>
    public WorkflowChatHistoryProvider ChatHistoryProvider { get; }

    /// <summary>
    /// Captures the outcome of creating or resuming a workflow run,
    /// indicating what types of messages were sent during resume.
    /// </summary>
    private readonly struct ResumeRunResult
    {
        /// <summary>The streaming run that was created or resumed.</summary>
        public StreamingRun Run { get; }

        /// <summary>Whether any external responses (e.g., <see cref="FunctionResultContent"/>) were delivered.</summary>
        public bool HasMatchedExternalResponses { get; }

        public ResumeRunResult(StreamingRun run, bool hasMatchedExternalResponses = false)
        {
            this.Run = Throw.IfNull(run);
            this.HasMatchedExternalResponses = hasMatchedExternalResponses;
        }
    }

    internal sealed class SessionState(
        string sessionId,
        CheckpointInfo? lastCheckpoint,
        InMemoryCheckpointManager? checkpointManager = null,
        AgentSessionStateBag? stateBag = null)
    {
        public string SessionId { get; } = sessionId;
        public CheckpointInfo? LastCheckpoint { get; } = lastCheckpoint;
        public InMemoryCheckpointManager? CheckpointManager { get; } = checkpointManager;
        public AgentSessionStateBag StateBag { get; } = stateBag ?? new();
    }
}
