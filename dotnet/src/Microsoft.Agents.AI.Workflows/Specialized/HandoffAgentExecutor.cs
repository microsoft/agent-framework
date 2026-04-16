// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class HandoffAgentExecutorOptions
{
    public HandoffAgentExecutorOptions(string? handoffInstructions, bool emitAgentResponseEvents, bool? emitAgentResponseUpdateEvents, HandoffToolCallFilteringBehavior toolCallFilteringBehavior)
    {
        this.HandoffInstructions = handoffInstructions;
        this.EmitAgentResponseEvents = emitAgentResponseEvents;
        this.EmitAgentResponseUpdateEvents = emitAgentResponseUpdateEvents;
        this.ToolCallFilteringBehavior = toolCallFilteringBehavior;
    }

    public string? HandoffInstructions { get; set; }

    public bool EmitAgentResponseEvents { get; set; }

    public bool? EmitAgentResponseUpdateEvents { get; set; }

    public HandoffToolCallFilteringBehavior ToolCallFilteringBehavior { get; set; } = HandoffToolCallFilteringBehavior.HandoffOnly;
}

internal struct AgentInvocationResult(AgentResponse agentResponse, string? handoffTargetId)
{
    public AgentResponse Response => agentResponse;

    public string? HandoffTargetId => handoffTargetId;

    [MemberNotNullWhen(true, nameof(HandoffTargetId))]
    public bool IsHandoffRequested => this.HandoffTargetId != null;
}

internal record HandoffAgentHostState(
    HandoffState? IncomingState,
    int ConversationBookmark)
{
    [MemberNotNullWhen(true, nameof(IncomingState))]
    [JsonIgnore]
    public bool IsTakingTurn => this.IncomingState != null;
}

internal sealed record StateRef<TState>(string Key, string? ScopeName)
{
    public ValueTask InvokeWithStateAsync(Func<TState?, IWorkflowContext, CancellationToken, ValueTask<TState?>> invocation,
                                          IWorkflowContext context,
                                          CancellationToken cancellationToken)
        => context.InvokeWithStateAsync(invocation, this.Key, this.ScopeName, cancellationToken);

    public ValueTask InvokeWithStateAsync(Func<TState?, IWorkflowContext, CancellationToken, ValueTask> invocation,
                                                 IWorkflowContext context,
                                                 CancellationToken cancellationToken)
        => context.InvokeWithStateAsync<TState>(
              async (state, ctx, ct) =>
              {
                  await invocation(state, ctx, ct).ConfigureAwait(false);
                  return state;
              }, this.Key, this.ScopeName, cancellationToken);
}

/// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
[Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
internal sealed class HandoffAgentExecutor :
    StatefulExecutor<HandoffAgentHostState, HandoffState>
{
    private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
        ([Description("The reason for the handoff")] string? reasonForHandoff) => { }).JsonSchema;

    public static string IdFor(AIAgent agent) => agent.GetDescriptiveId();

    private readonly AIAgent _agent;
    private readonly ChatClientAgentRunOptions? _agentOptions;

    private readonly HandoffAgentExecutorOptions _options;

    private readonly HashSet<string> _handoffFunctionNames = [];
    private readonly Dictionary<string, string> _handoffFunctionToAgentId = [];

    private readonly StateRef<HandoffSharedState> _sharedStateRef = new(HandoffConstants.HandoffSharedStateKey,
                                                                        HandoffConstants.HandoffSharedStateScope);

    internal const string AgentSessionKey = nameof(AgentSession);
    private AgentSession? _session;

    private static HandoffAgentHostState InitialStateFactory() => new(null, 0);

    public HandoffAgentExecutor(AIAgent agent, HashSet<HandoffTarget> handoffs, HandoffAgentExecutorOptions options)
        : base(IdFor(agent), InitialStateFactory)
    {
        this._agent = agent;
        this._options = options;

        this._agentOptions = CreateAgentHandoffContext(this._options.HandoffInstructions, handoffs, this._handoffFunctionNames, this._handoffFunctionToAgentId);
    }

    private static ChatClientAgentRunOptions? CreateAgentHandoffContext(string? handoffInstructions, HashSet<HandoffTarget> handoffs, HashSet<string> functionNames, Dictionary<string, string> functionToAgentId)
    {
        ChatClientAgentRunOptions? result = null;

        if (handoffs.Count != 0)
        {
            result = new()
            {
                ChatOptions = new()
                {
                    AllowMultipleToolCalls = false,
                    Instructions = handoffInstructions,
                    Tools = [],
                },
            };

            int index = 0;
            foreach (HandoffTarget handoff in handoffs)
            {
                index++;
                var handoffFunc = AIFunctionFactory.CreateDeclaration($"{HandoffWorkflowBuilder.FunctionPrefix}{index}", handoff.Reason, s_handoffSchema);

                functionNames.Add(handoffFunc.Name);
                functionToAgentId[handoffFunc.Name] = handoff.Target.Id;

                result.ChatOptions.Tools.Add(handoffFunc);
            }
        }

        return result;
    }

    private AIContentExternalHandler<ToolApprovalRequestContent, ToolApprovalResponseContent>? _userInputHandler;
    private AIContentExternalHandler<FunctionCallContent, FunctionResultContent>? _functionCallHandler;

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return this.ConfigureUserInputHandling(base.ConfigureProtocol(protocolBuilder))
                   .SendsMessage<HandoffState>();
    }

    private ProtocolBuilder ConfigureUserInputHandling(ProtocolBuilder protocolBuilder)
    {
        this._userInputHandler = new AIContentExternalHandler<ToolApprovalRequestContent, ToolApprovalResponseContent>(
            ref protocolBuilder,
            portId: $"{this.Id}_UserInput",
            intercepted: false,
            handler: this.HandleUserInputResponseAsync);

        this._functionCallHandler = new AIContentExternalHandler<FunctionCallContent, FunctionResultContent>(
            ref protocolBuilder,
            portId: $"{this.Id}_FunctionCall",
            intercepted: false, // TODO: Use this instead of manual function handling for handoff?
            handler: this.HandleFunctionResultAsync);

        return protocolBuilder;
    }

    private ValueTask HandleUserInputResponseAsync(
        ToolApprovalResponseContent response,
        IWorkflowContext context,
        CancellationToken cancellationToken)
    {
        if (!this._userInputHandler!.MarkRequestAsHandled(response.RequestId))
        {
            throw new InvalidOperationException($"No pending ToolApprovalRequest found with id '{response.RequestId}'.");
        }

        // Merge the external response with any already-buffered regular messages so mixed-content
        // resumes can be processed in one invocation.
        return this.InvokeWithStateAsync((state, ctx, ct) =>
        {
            if (!state.IsTakingTurn)
            {
                throw new InvalidOperationException("Cannot process user responses when not taking a turn in Handoff Orchestration.");
            }

            ChatMessage userMessage = new(ChatRole.User, [response])
            {
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
            };

            return this.ContinueTurnAsync(state, [userMessage], ctx, ct);
        }, context, skipCache: false, cancellationToken);
    }

    private ValueTask HandleFunctionResultAsync(
        FunctionResultContent result,
        IWorkflowContext context,
        CancellationToken cancellationToken)
    {
        if (!this._functionCallHandler!.MarkRequestAsHandled(result.CallId))
        {
            throw new InvalidOperationException($"No pending FunctionCall found with id '{result.CallId}'.");
        }

        // Merge the external response with any already-buffered regular messages so mixed-content
        // resumes can be processed in one invocation.
        return this.InvokeWithStateAsync((state, ctx, ct) =>
        {
            if (!state.IsTakingTurn)
            {
                throw new InvalidOperationException("Cannot process user responses in when not taking a turn in Handoff Orchestration.");
            }

            ChatMessage toolMessage = new(ChatRole.Tool, [result])
            {
                AuthorName = this._agent.Name ?? this._agent.Id,
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
            };

            return this.ContinueTurnAsync(state, [toolMessage], ctx, ct);
        }, context, skipCache: false, cancellationToken);
    }

    private async ValueTask<HandoffAgentHostState?> ContinueTurnAsync(HandoffAgentHostState state, List<ChatMessage> incomingMessages, IWorkflowContext context, CancellationToken cancellationToken, bool skipAddIncoming = false)
    {
        if (!state.IsTakingTurn)
        {
            throw new InvalidOperationException("Cannot process user responses in when not taking a turn in Handoff Orchestration.");
        }

        // If a handoff was invoked by a previous agent, filter out the handoff function call and tool result messages
        // before sending to the underlying agent. These are internal workflow mechanics that confuse the target model
        // into ignoring the original user question.
        //
        // This will not filter out tool responses and approval responses that are part of this agent's turn, which is
        // the expected behavior since those are part of the agent's reasoning process.
        HandoffMessagesFilter handoffMessagesFilter = new(this._options.ToolCallFilteringBehavior);
        IEnumerable<ChatMessage> messagesForAgent = state.IncomingState.RequestedHandoffTargetAgentId is not null
                                                  ? handoffMessagesFilter.FilterMessages(incomingMessages)
                                                  : incomingMessages;

        List<ChatMessage>? roleChanges = messagesForAgent.ChangeAssistantToUserForOtherParticipants(this._agent.Name ?? this._agent.Id);

        bool emitUpdateEvents = state.IncomingState!.ShouldEmitStreamingEvents(this._options.EmitAgentResponseUpdateEvents);
        AgentInvocationResult result = await this.InvokeAgentAsync(messagesForAgent, context, emitUpdateEvents, cancellationToken)
                                                     .ConfigureAwait(false);

        if (this.HasOutstandingRequests && result.IsHandoffRequested)
        {
            throw new InvalidOperationException("Cannot request a handoff while holding pending requests.");
        }

        roleChanges.ResetUserToAssistantForChangedRoles();

        int newConversationBookmark = state.ConversationBookmark;
        await this._sharedStateRef.InvokeWithStateAsync(
            (sharedState, ctx, ct) =>
            {
                if (sharedState == null)
                {
                    throw new InvalidOperationException("Handoff Orchestration shared state was not properly initialized.");
                }

                if (!skipAddIncoming)
                {
                    sharedState.Conversation.AddMessages(incomingMessages);
                }

                newConversationBookmark = sharedState.Conversation.AddMessages(result.Response.Messages);

                return new ValueTask();
            },
            context,
            cancellationToken).ConfigureAwait(false);

        // We send on the HandoffState even if handoff is not requested because we might be terminating the processing, but this only
        // happens if we have no outstanding requests.
        if (!this.HasOutstandingRequests)
        {
            HandoffState outgoingState = new(state.IncomingState.TurnToken, result.HandoffTargetId, this._agent.Id);

            await context.SendMessageAsync(outgoingState, cancellationToken).ConfigureAwait(false);

            // reset the state for the next handoff, making sure to keep track of the conversation bookmark, and avoid resetting the
            // agent session. (return-to-current is modeled as a new handoff turn, as opposed to "HITL", which can be a bit confusing.)
            return state with { IncomingState = null, ConversationBookmark = newConversationBookmark };
        }

        return state;
    }

    public override ValueTask HandleAsync(HandoffState message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.InvokeWithStateAsync(InvokeContinueTurnAsync, context, skipCache: false, cancellationToken);

        async ValueTask<HandoffAgentHostState?> InvokeContinueTurnAsync(HandoffAgentHostState state, IWorkflowContext context, CancellationToken cancellationToken)
        {
            // Check that we are not getting this message while in the middle of a turn
            if (state.IsTakingTurn)
            {
                throw new InvalidOperationException("Cannot have multiple simultaneous conversations in Handoff Orchestration.");
            }

            IEnumerable<ChatMessage> newConversationMessages = [];
            int newConversationBookmark = 0;

            await this._sharedStateRef.InvokeWithStateAsync(
                (sharedState, ctx, ct) =>
                {
                    if (sharedState == null)
                    {
                        throw new InvalidOperationException("Handoff Orchestration shared state was not properly initialized.");
                    }

                    (newConversationMessages, newConversationBookmark) = sharedState.Conversation.CollectNewMessages(state.ConversationBookmark);

                    return new ValueTask();
                },
                context,
                cancellationToken).ConfigureAwait(false);

            state = state with { IncomingState = message, ConversationBookmark = newConversationBookmark };

            return await this.ContinueTurnAsync(state, newConversationMessages.ToList(), context, cancellationToken, skipAddIncoming: true)
                             .ConfigureAwait(false);
        }
    }

    private const string UserInputRequestStateKey = nameof(_userInputHandler);
    private const string FunctionCallRequestStateKey = nameof(_functionCallHandler);

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task userInputRequestsTask = this._userInputHandler?.OnCheckpointingAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRequestsTask = this._functionCallHandler?.OnCheckpointingAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task agentSessionTask = CheckpointAgentSessionAsync();

        Task baseTask = base.OnCheckpointingAsync(context, cancellationToken).AsTask();
        await Task.WhenAll(userInputRequestsTask, functionCallRequestsTask, agentSessionTask, baseTask).ConfigureAwait(false);

        async Task CheckpointAgentSessionAsync()
        {
            JsonElement? sessionState = this._session is not null ? await this._agent.SerializeSessionAsync(this._session, cancellationToken: cancellationToken).ConfigureAwait(false) : null;
            await context.QueueStateUpdateAsync(AgentSessionKey, sessionState, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task userInputRestoreTask = this._userInputHandler?.OnCheckpointRestoredAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRestoreTask = this._functionCallHandler?.OnCheckpointRestoredAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task agentSessionTask = RestoreAgentSessionAsync();

        await Task.WhenAll(userInputRestoreTask, functionCallRestoreTask, agentSessionTask).ConfigureAwait(false);
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        async Task RestoreAgentSessionAsync()
        {
            JsonElement? sessionState = await context.ReadStateAsync<JsonElement?>(AgentSessionKey, cancellationToken: cancellationToken).ConfigureAwait(false);
            if (sessionState.HasValue)
            {
                this._session = await this._agent.DeserializeSessionAsync(sessionState.Value, cancellationToken: cancellationToken).ConfigureAwait(false);
            }
        }
    }
    private bool HasOutstandingRequests => (this._userInputHandler?.HasPendingRequests == true)
                                        || (this._functionCallHandler?.HasPendingRequests == true);

    private async ValueTask<AgentInvocationResult> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, bool emitUpdateEvents, CancellationToken cancellationToken = default)
    {
        AgentResponse response;

        AIAgentUnservicedRequestsCollector collector = new(this._userInputHandler, this._functionCallHandler);

        string? requestedHandoff = null;
        List<AgentResponseUpdate> updates = [];
        List<FunctionCallContent> candidateRequests = [];

        await this.InvokeWithStateAsync(
            async (state, ctx, ct) =>
            {
                this._session ??= await this._agent.CreateSessionAsync(ct).ConfigureAwait(false);

                IAsyncEnumerable<AgentResponseUpdate> agentStream =
                    this._agent.RunStreamingAsync(messages,
                                                  this._session,
                                                  options: this._agentOptions,
                                                  cancellationToken: ct);

                await foreach (AgentResponseUpdate update in agentStream.ConfigureAwait(false))
                {
                    await AddUpdateAsync(update, ct).ConfigureAwait(false);

                    collector.ProcessAgentResponseUpdate(update, CollectHandoffRequestsFilter);

                    bool CollectHandoffRequestsFilter(FunctionCallContent candidateHandoffRequest)
                    {
                        bool isHandoffRequest = this._handoffFunctionNames.Contains(candidateHandoffRequest.Name);
                        if (isHandoffRequest)
                        {
                            candidateRequests.Add(candidateHandoffRequest);
                        }

                        return !isHandoffRequest;
                    }
                }

                return state;
            },
            context,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        if (candidateRequests.Count > 1)
        {
            string message = $"Duplicate handoff requests in single turn ([{string.Join(", ", candidateRequests.Select(request => request.Name))}]). Using last ({candidateRequests.Last().Name})";
            await context.AddEventAsync(new WorkflowWarningEvent(message), cancellationToken).ConfigureAwait(false);
        }

        if (candidateRequests.Count > 0)
        {
            FunctionCallContent handoffRequest = candidateRequests[candidateRequests.Count - 1];
            requestedHandoff = handoffRequest.Name;

            await AddUpdateAsync(
                    new AgentResponseUpdate
                    {
                        AgentId = this._agent.Id,
                        AuthorName = this._agent.Name ?? this._agent.Id,
                        Contents = [new FunctionResultContent(handoffRequest.CallId, "Transferred.")],
                        CreatedAt = DateTimeOffset.UtcNow,
                        MessageId = Guid.NewGuid().ToString("N"),
                        Role = ChatRole.Tool,
                    },
                    cancellationToken
                 )
                .ConfigureAwait(false);
        }

        response = updates.ToAgentResponse();

        if (this._options.EmitAgentResponseEvents)
        {
            await context.YieldOutputAsync(response, cancellationToken).ConfigureAwait(false);
        }

        await collector.SubmitAsync(context, cancellationToken).ConfigureAwait(false);

        return new(response, LookupHandoffTarget(requestedHandoff));

        ValueTask AddUpdateAsync(AgentResponseUpdate update, CancellationToken cancellationToken)
        {
            updates.Add(update);

            return emitUpdateEvents ? context.YieldOutputAsync(update, cancellationToken) : default;
        }

        string? LookupHandoffTarget(string? requestedHandoff)
            => requestedHandoff != null
             ? this._handoffFunctionToAgentId.TryGetValue(requestedHandoff, out string? targetId) ? targetId : null
             : null;
    }
}
