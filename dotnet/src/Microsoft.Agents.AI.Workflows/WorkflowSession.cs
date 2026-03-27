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

    /// <summary>
    /// Tracks pending external requests by their workflow-facing request ID.
    /// This mapping enables converting incoming response content back to <see cref="ExternalResponse"/>
    /// when resuming a workflow from a checkpoint.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Entries are added when a <see cref="RequestInfoEvent"/> is received during workflow execution,
    /// and removed when a matching response is delivered via <see cref="SendMessagesWithResponseConversionAsync"/>.
    /// </para>
    /// <para>
    /// The number of entries is bounded by the number of outstanding external requests in a single workflow run.
    /// When a session is abandoned, all pending requests are released with the session object.
    /// Request-level timeouts, if needed, should be implemented in the workflow definition itself
    /// (e.g., using a timer racing against an external event).
    /// </para>
    /// </remarks>
    private readonly Dictionary<string, ExternalRequest> _pendingRequests = [];

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
        this._pendingRequests = sessionState.PendingRequests ?? [];
    }

    public CheckpointInfo? LastCheckpoint { get; set; }

    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonMarshaller marshaller = new(jsonSerializerOptions);
        SessionState info = new(
            this.SessionId,
            this.LastCheckpoint,
            this._inMemoryCheckpointManager,
            this.StateBag,
            this._pendingRequests);

        return marshaller.Marshal(info);
    }

    public AgentResponseUpdate CreateUpdate(string responseId, object raw, params AIContent[] parts)
    {
        Throw.IfNullOrEmpty(parts);

        return new(ChatRole.Assistant, parts)
        {
            CreatedAt = DateTimeOffset.UtcNow,
            MessageId = Guid.NewGuid().ToString("N"),
            Role = ChatRole.Assistant,
            ResponseId = responseId,
            RawRepresentation = raw
        };
    }

    public AgentResponseUpdate CreateUpdate(string responseId, object raw, ChatMessage message)
    {
        Throw.IfNull(message);

        return new(message.Role, message.Contents)
        {
            CreatedAt = message.CreatedAt ?? DateTimeOffset.UtcNow,
            MessageId = message.MessageId ?? Guid.NewGuid().ToString("N"),
            ResponseId = responseId,
            RawRepresentation = raw
        };
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
            ResumeDispatchInfo dispatchInfo = await this.SendMessagesWithResponseConversionAsync(run, messages).ConfigureAwait(false);
            return new ResumeRunResult(run, dispatchInfo);
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
    /// Structured information about how resume content was dispatched.
    /// </returns>
    private async ValueTask<ResumeDispatchInfo> SendMessagesWithResponseConversionAsync(StreamingRun run, List<ChatMessage> messages)
    {
        List<ChatMessage> regularMessages = [];
        // Responses are deferred until after regular messages are queued so response handlers
        // can merge buffered regular content in the same continuation turn.
        List<(ExternalResponse Response, string RequestId)> externalResponses = [];
        bool hasMatchedResponseForStartExecutor = false;

        // Tracks content IDs already matched to pending requests within this invocation,
        // preventing duplicate responses for the same ID from being sent to the workflow engine.
        HashSet<string>? matchedContentIds = null;

        foreach (ChatMessage message in messages)
        {
            List<AIContent> regularContents = [];

            foreach (AIContent content in message.Contents)
            {
                string? contentId = GetResponseContentId(content);

                // Skip duplicate response content for an already-matched content ID
                if (contentId != null && matchedContentIds?.Contains(contentId) == true)
                {
                    continue;
                }

                if (contentId != null
                    && this.TryGetPendingRequest(contentId) is ExternalRequest pendingRequest)
                {
                    // For intercepted/complex topologies the port may not be registered in the EdgeMap.
                    // Treat unknown port as non-start-executor (conservative): TurnToken will still be sent.
                    if (run.TryGetResponsePortExecutorId(pendingRequest.PortInfo.PortId, out string? responseExecutorId))
                    {
                        hasMatchedResponseForStartExecutor |= string.Equals(responseExecutorId, this._workflow.StartExecutorId, StringComparison.Ordinal);
                    }

                    AIContent normalizedResponseContent = NormalizeResponseContentForDelivery(content, pendingRequest);
                    externalResponses.Add((pendingRequest.CreateResponse(normalizedResponseContent), pendingRequest.RequestId));
                    (matchedContentIds ??= new(StringComparer.Ordinal)).Add(contentId);
                }
                else
                {
                    regularContents.Add(content);
                }
            }

            if (regularContents.Count > 0)
            {
                ChatMessage cloned = message.Clone();
                cloned.Contents = regularContents;
                regularMessages.Add(cloned);
            }
        }

        // Send regular messages first so response handlers can merge them with responses.
        bool hasRegularMessages = regularMessages.Count > 0;
        if (hasRegularMessages)
        {
            await run.TrySendMessageAsync(regularMessages).ConfigureAwait(false);
        }

        // Send external responses after regular messages.
        bool hasMatchedExternalResponses = false;
        foreach ((ExternalResponse response, string requestId) in externalResponses)
        {
            await run.SendResponseAsync(response).ConfigureAwait(false);
            hasMatchedExternalResponses = true;
            this.RemovePendingRequest(requestId);
        }

        return new ResumeDispatchInfo(
            hasRegularMessages,
            hasMatchedExternalResponses,
            hasMatchedResponseForStartExecutor);
    }

    /// <summary>
    /// Creates the workflow-facing request content surfaced in response updates.
    /// </summary>
    private static AIContent CreateRequestContentForDelivery(ExternalRequest request) => request switch
    {
        ExternalRequest externalRequest when externalRequest.TryGetDataAs(out FunctionCallContent? functionCallContent)
            => CloneFunctionCallContent(functionCallContent, externalRequest.RequestId),
        ExternalRequest externalRequest when externalRequest.TryGetDataAs(out ToolApprovalRequestContent? toolApprovalRequestContent)
            => CloneToolApprovalRequestContent(toolApprovalRequestContent, externalRequest.RequestId),
        ExternalRequest externalRequest
            => externalRequest.ToFunctionCall(),
    };

    /// <summary>
    /// Rewrites workflow-facing response content back to the original agent-owned content ID.
    /// </summary>
    private static AIContent NormalizeResponseContentForDelivery(AIContent content, ExternalRequest request) => content switch
    {
        FunctionResultContent functionResultContent when request.TryGetDataAs(out FunctionCallContent? functionCallContent)
            => CloneFunctionResultContent(functionResultContent, functionCallContent.CallId),
        ToolApprovalResponseContent toolApprovalResponseContent when request.TryGetDataAs(out ToolApprovalRequestContent? toolApprovalRequestContent)
            => CloneToolApprovalResponseContent(toolApprovalResponseContent, toolApprovalRequestContent.RequestId),
        _ => content,
    };

    /// <summary>
    /// Gets the workflow-facing request ID from response content types.
    /// </summary>
    private static string? GetResponseContentId(AIContent content) => content switch
    {
        FunctionResultContent functionResultContent => functionResultContent.CallId,
        ToolApprovalResponseContent toolApprovalResponseContent => toolApprovalResponseContent.RequestId,
        _ => null
    };

    /// <summary>
    /// Tries to get a pending request by workflow-facing request ID.
    /// </summary>
    private ExternalRequest? TryGetPendingRequest(string requestId) =>
        this._pendingRequests.TryGetValue(requestId, out ExternalRequest? request) ? request : null;

    /// <summary>
    /// Adds a pending request indexed by workflow-facing request ID.
    /// </summary>
    private void AddPendingRequest(string requestId, ExternalRequest request) => this._pendingRequests[requestId] = request;

    /// <summary>
    /// Removes a pending request by workflow-facing request ID.
    /// </summary>
    private void RemovePendingRequest(string requestId) =>
        this._pendingRequests.Remove(requestId);

    internal async
    IAsyncEnumerable<AgentResponseUpdate> InvokeStageAsync(
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.LastResponseId = Guid.NewGuid().ToString("N");
        List<ChatMessage> messages = this.ChatHistoryProvider.GetFromBookmark(this).ToList();

        ResumeRunResult resumeResult =
            await this.CreateOrResumeRunAsync(messages, cancellationToken).ConfigureAwait(false);

#pragma warning disable CA2007 // Analyzer misfiring.
        await using StreamingRun run = resumeResult.Run;
#pragma warning restore CA2007

        ResumeDispatchInfo dispatchInfo = resumeResult.DispatchInfo;

        // Send a TurnToken to the start executor unless the only activity is an external
        // response directed at the start executor itself (which self-emits a TurnToken via
        // ContinueTurnAsync). Non-start executors (e.g., RequestInfoExecutor) do not emit
        // TurnTokens after processing responses, so the session must always provide one.
        bool shouldSendTurnToken =
            !dispatchInfo.HasMatchedExternalResponses
            || !dispatchInfo.HasMatchedResponseForStartExecutor;
        if (shouldSendTurnToken)
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
                    AIContent requestContent = CreateRequestContentForDelivery(requestInfo.Request);

                    // Track the pending request so we can convert incoming responses back to ExternalResponse.
                    // External callers respond using the workflow-facing request ID, which is always RequestId.
                    this.AddPendingRequest(requestInfo.Request.RequestId, requestInfo.Request);

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

        /// <summary>How resume-time content was dispatched into the workflow runtime.</summary>
        public ResumeDispatchInfo DispatchInfo { get; }

        public ResumeRunResult(StreamingRun run, ResumeDispatchInfo dispatchInfo = default)
        {
            this.Run = Throw.IfNull(run);
            this.DispatchInfo = dispatchInfo;
        }
    }

    /// <summary>
    /// Captures how resumed input was split across regular-message and external-response delivery paths.
    /// </summary>
    private readonly struct ResumeDispatchInfo
    {
        public ResumeDispatchInfo(bool hasRegularMessages, bool hasMatchedExternalResponses, bool hasMatchedResponseForStartExecutor)
        {
            this.HasRegularMessages = hasRegularMessages;
            this.HasMatchedExternalResponses = hasMatchedExternalResponses;
            this.HasMatchedResponseForStartExecutor = hasMatchedResponseForStartExecutor;
        }

        public bool HasRegularMessages { get; }

        public bool HasMatchedExternalResponses { get; }

        public bool HasMatchedResponseForStartExecutor { get; }
    }

    /// <summary>
    /// Clones a <see cref="FunctionCallContent"/> with a workflow-facing call ID.
    /// </summary>
    private static FunctionCallContent CloneFunctionCallContent(FunctionCallContent content, string callId)
    {
        FunctionCallContent clone = new(callId, content.Name, content.Arguments)
        {
            Exception = content.Exception,
            InformationalOnly = content.InformationalOnly,
        };

        return CopyContentMetadata(content, clone);
    }

    /// <summary>
    /// Clones a <see cref="FunctionResultContent"/> with an agent-owned call ID.
    /// </summary>
    private static FunctionResultContent CloneFunctionResultContent(FunctionResultContent content, string callId)
    {
        FunctionResultContent clone = new(callId, content.Result)
        {
            Exception = content.Exception,
        };

        return CopyContentMetadata(content, clone);
    }

    /// <summary>
    /// Clones a <see cref="ToolApprovalRequestContent"/> with a workflow-facing request ID.
    /// </summary>
    private static ToolApprovalRequestContent CloneToolApprovalRequestContent(ToolApprovalRequestContent content, string id)
    {
        ToolApprovalRequestContent clone = new(id, content.ToolCall);
        return CopyContentMetadata(content, clone);
    }

    /// <summary>
    /// Clones a <see cref="ToolApprovalResponseContent"/> with an agent-owned request ID.
    /// </summary>
    private static ToolApprovalResponseContent CloneToolApprovalResponseContent(ToolApprovalResponseContent content, string id)
    {
        ToolApprovalResponseContent clone = new(id, content.Approved, content.ToolCall)
        {
            Reason = content.Reason,
        };

        return CopyContentMetadata(content, clone);
    }

    /// <summary>
    /// Copies shared <see cref="AIContent"/> metadata to a cloned content instance.
    /// </summary>
    private static TContent CopyContentMetadata<TContent>(AIContent source, TContent target)
        where TContent : AIContent
    {
        target.AdditionalProperties = source.AdditionalProperties;
        target.Annotations = source.Annotations;
        target.RawRepresentation = source.RawRepresentation;
        return target;
    }

    internal sealed class SessionState(
        string sessionId,
        CheckpointInfo? lastCheckpoint,
        InMemoryCheckpointManager? checkpointManager = null,
        AgentSessionStateBag? stateBag = null,
        Dictionary<string, ExternalRequest>? pendingRequests = null)
    {
        public string SessionId { get; } = sessionId;
        public CheckpointInfo? LastCheckpoint { get; } = lastCheckpoint;
        public InMemoryCheckpointManager? CheckpointManager { get; } = checkpointManager;
        public AgentSessionStateBag StateBag { get; } = stateBag ?? new();
        public Dictionary<string, ExternalRequest>? PendingRequests { get; } = pendingRequests;
    }
}
