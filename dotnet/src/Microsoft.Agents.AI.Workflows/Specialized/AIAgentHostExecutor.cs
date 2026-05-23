// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal record AIAgentHostState(JsonElement? ThreadState, bool? CurrentTurnEmitEvents);

internal static class TurnExtensions
{
    public static bool ShouldEmitStreamingEvents(this TurnToken token, bool? agentSetting)
        => token.EmitEvents ?? agentSetting ?? false;

    public static bool ShouldEmitStreamingEvents(bool? turnTokenSetting, bool? agentSetting)
        => turnTokenSetting ?? agentSetting ?? false;

    public static bool ShouldEmitStreamingEvents(this HandoffState handoffState, bool? agentSetting)
        => handoffState.TurnToken.ShouldEmitStreamingEvents(agentSetting);
}

internal class AIAgentHostExecutor : ChatProtocolExecutor
{
    private readonly AIAgent _agent;
    private readonly AIAgentHostOptions _options;
    private AgentSession? _session;
    private bool? _currentTurnEmitEvents;

    private AIContentExternalHandler<ToolApprovalRequestContent, ToolApprovalResponseContent>? _userInputHandler;
    private AIContentExternalHandler<FunctionCallContent, FunctionResultContent>? _functionCallHandler;

    private static readonly ChatProtocolExecutorOptions s_defaultChatProtocolOptions = new()
    {
        AutoSendTurnToken = false,
        StringMessageChatRole = ChatRole.User
    };

    public static string IdFor(AIAgent agent) => agent.GetDescriptiveId();

    public AIAgentHostExecutor(AIAgent agent, AIAgentHostOptions options) : base(id: IdFor(agent),
                                                                                 s_defaultChatProtocolOptions,
                                                                                 declareCrossRunShareable: false) // Explicitly false, because we maintain turn state on the instance
    {
        this._agent = agent;
        this._options = options;
    }

    private ProtocolBuilder ConfigureUserInputHandling(ProtocolBuilder protocolBuilder)
    {
        this._userInputHandler = new AIContentExternalHandler<ToolApprovalRequestContent, ToolApprovalResponseContent>(
            ref protocolBuilder,
            portId: $"{this.Id}_UserInput",
            intercepted: this._options.InterceptUserInputRequests,
            handler: this.HandleUserInputResponseAsync);

        this._functionCallHandler = new AIContentExternalHandler<FunctionCallContent, FunctionResultContent>(
            ref protocolBuilder,
            portId: $"{this.Id}_FunctionCall",
            intercepted: this._options.InterceptUnterminatedFunctionCalls,
            handler: this.HandleFunctionResultAsync);

        return protocolBuilder;
    }

    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        return this.ConfigureUserInputHandling(base.ConfigureProtocol(protocolBuilder))
                   .ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<ResetChatSignal>(this.ResetChat));
    }

    internal void ResetChat(ResetChatSignal signal, IWorkflowContext context)
    {
        this._session = null;
        this._currentTurnEmitEvents = null;
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
        return this.ProcessTurnMessagesAsync(async (pendingMessages, ctx, ct) =>
        {
            pendingMessages.Add(new ChatMessage(ChatRole.User, [response])
            {
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
            });

            await this.ContinueTurnAsync(pendingMessages, ctx, this._currentTurnEmitEvents ?? false, ct).ConfigureAwait(false);

            // Clear the buffered turn messages because they were consumed by ContinueTurnAsync.
            return null;
        }, context, cancellationToken);
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
        return this.ProcessTurnMessagesAsync(async (pendingMessages, ctx, ct) =>
        {
            pendingMessages.Add(new ChatMessage(ChatRole.Tool, [result])
            {
                AuthorName = this._agent.Name ?? this._agent.Id,
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
            });

            await this.ContinueTurnAsync(pendingMessages, ctx, this._currentTurnEmitEvents ?? false, ct).ConfigureAwait(false);

            // Clear the buffered turn messages because they were consumed by ContinueTurnAsync.
            return null;
        }, context, cancellationToken);
    }

    private async ValueTask<AgentSession> EnsureSessionAsync(IWorkflowContext context, CancellationToken cancellationToken) =>
        this._session ??= await this._agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

    private const string UserInputRequestStateKey = nameof(_userInputHandler);
    private const string FunctionCallRequestStateKey = nameof(_functionCallHandler);
    private const string AIAgentHostStateKey = nameof(AIAgentHostState);

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        JsonElement? sessionState = this._session is not null ? await this._agent.SerializeSessionAsync(this._session, cancellationToken: cancellationToken).ConfigureAwait(false) : null;
        AIAgentHostState state = new(sessionState, this._currentTurnEmitEvents);
        Task coreStateTask = context.QueueStateUpdateAsync(AIAgentHostStateKey, state, cancellationToken: cancellationToken).AsTask();
        Task userInputRequestsTask = this._userInputHandler?.OnCheckpointingAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRequestsTask = this._functionCallHandler?.OnCheckpointingAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;

        Task baseTask = base.OnCheckpointingAsync(context, cancellationToken).AsTask();

        await Task.WhenAll(coreStateTask, userInputRequestsTask, functionCallRequestsTask, baseTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task userInputRestoreTask = this._userInputHandler?.OnCheckpointRestoredAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRestoreTask = this._functionCallHandler?.OnCheckpointRestoredAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;

        AIAgentHostState? state = await context.ReadStateAsync<AIAgentHostState>(AIAgentHostStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (state != null)
        {
            this._session = state.ThreadState.HasValue
                         ? await this._agent.DeserializeSessionAsync(state.ThreadState.Value, cancellationToken: cancellationToken).ConfigureAwait(false)
                         : null;
            this._currentTurnEmitEvents = state.CurrentTurnEmitEvents;
        }

        await Task.WhenAll(userInputRestoreTask, functionCallRestoreTask).ConfigureAwait(false);
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);
    }

    private bool HasOutstandingRequests => (this._userInputHandler?.HasPendingRequests == true)
                                        || (this._functionCallHandler?.HasPendingRequests == true);

    // While we save this on the instance, we are not cross-run shareable, but as AgentBinding uses the factory pattern this is not an issue
    private async ValueTask ContinueTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool emitEvents, CancellationToken cancellationToken)
    {
        this._currentTurnEmitEvents = emitEvents;
        if (this._options.ForwardIncomingMessages)
        {
            await context.SendMessageAsync(messages, cancellationToken).ConfigureAwait(false);
        }

        IEnumerable<ChatMessage> filteredMessages = this._options.ReassignOtherAgentsAsUsers
                                                  ? messages.Select(m => m.ChatAssistantToUserIfNotFromNamed(this._agent.Name ?? this._agent.Id))
                                                  : messages;

        AgentResponse response = await this.InvokeAgentAsync(filteredMessages, context, emitEvents, cancellationToken).ConfigureAwait(false);

        // Filter out server-side artifacts (reasoning tokens, web search calls, etc.)
        // that are internal to this agent. Forwarding them to other agents in the workflow
        // causes invalid request errors when the receiving agent uses the Responses API,
        // because these item types are not valid as input items.
        List<ChatMessage> forwardableMessages = FilterForwardableMessages(response.Messages).ToList();
        if (forwardableMessages.Count > 0)
        {
            await context.SendMessageAsync(forwardableMessages, cancellationToken)
                         .ConfigureAwait(false);
        }

        // If we have no outstanding requests, we can yield a turn token back to the workflow.
        if (!this.HasOutstandingRequests)
        {
            await context.SendMessageAsync(new TurnToken(this._currentTurnEmitEvents), cancellationToken).ConfigureAwait(false);
            this._currentTurnEmitEvents = null; // Possibly not actually necessary, but cleaning this up makes it clearer when debugging
        }
    }

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => this.ContinueTurnAsync(messages,
                                  context,
                                  TurnExtensions.ShouldEmitStreamingEvents(turnTokenSetting: emitEvents, this._options.EmitAgentUpdateEvents),
                                  cancellationToken);

    private async ValueTask<AgentResponse> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, bool emitUpdateEvents, CancellationToken cancellationToken = default)
    {
        AgentResponse response;
        AIAgentUnservicedRequestsCollector collector = new(this._userInputHandler, this._functionCallHandler);

        if (emitUpdateEvents)
        {
            // Run the agent in streaming mode only when agent run update events are to be emitted.
            IAsyncEnumerable<AgentResponseUpdate> agentStream = this._agent.RunStreamingAsync(
                messages,
                await this.EnsureSessionAsync(context, cancellationToken).ConfigureAwait(false),
                cancellationToken: cancellationToken);

            List<AgentResponseUpdate> updates = [];
            await foreach (AgentResponseUpdate update in agentStream.ConfigureAwait(false))
            {
                await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
                collector.ProcessAgentResponseUpdate(update);
                updates.Add(update);
            }

            response = updates.ToAgentResponse();
        }
        else
        {
            // Otherwise, run the agent in non-streaming mode.
            response = await this._agent.RunAsync(messages,
                                                  await this.EnsureSessionAsync(context, cancellationToken).ConfigureAwait(false),
                                                  cancellationToken: cancellationToken)
                                        .ConfigureAwait(false);

            collector.ProcessAgentResponse(response);
        }

        if (this._options.EmitAgentResponseEvents)
        {
            await context.YieldOutputAsync(response, cancellationToken).ConfigureAwait(false);
        }

        await collector.SubmitAsync(context, cancellationToken).ConfigureAwait(false);

        return response;
    }

    /// <summary>
    /// Content types that represent meaningful conversational content portable across agents.
    /// Messages containing only content types not in this set (e.g. reasoning tokens, web search
    /// calls) are filtered out before forwarding, as they are output-only items that cause
    /// schema validation errors when sent as input to the Responses API.
    /// </summary>
    private static readonly HashSet<Type> s_forwardableContentTypes =
    [
        typeof(TextContent),
        typeof(DataContent),
        typeof(UriContent),
        typeof(FunctionCallContent),
        typeof(FunctionResultContent),
        typeof(ToolApprovalRequestContent),
        typeof(ToolApprovalResponseContent),
        typeof(HostedFileContent),
        typeof(ErrorContent),
    ];

    /// <summary>
    /// Filters response messages to only include those with portable conversational content,
    /// and strips <see cref="ChatMessage.RawRepresentation"/> so that provider-specific output
    /// items (e.g. <c>mcp_list_tools</c>, <c>reasoning</c>, <c>fabric_dataagent_preview_call</c>)
    /// are not round-tripped by the M.E.AI library when the messages are sent to another agent.
    /// </summary>
    private static List<ChatMessage> FilterForwardableMessages(IList<ChatMessage> messages)
    {
        List<ChatMessage> result = [];

        foreach (ChatMessage message in messages)
        {
            // Extract only the content items that are portable across agents.
            List<AIContent> forwardableContents = message.Contents
                .Where(c => s_forwardableContentTypes.Any(t => t.IsAssignableFrom(c.GetType())))
                .ToList();

            if (forwardableContents.Count == 0)
            {
                continue;
            }

            // Build a clean message without the provider-specific RawRepresentation,
            // which would otherwise cause the M.E.AI library to round-trip the original
            // output-only items (e.g. mcp_list_tools) as input to the next agent.
            result.Add(new ChatMessage(message.Role, forwardableContents)
            {
                AuthorName = message.AuthorName,
                MessageId = message.MessageId,
                CreatedAt = message.CreatedAt,
                AdditionalProperties = message.AdditionalProperties is null ? null : new(message.AdditionalProperties),
            });
        }

        return result;
    }
}
