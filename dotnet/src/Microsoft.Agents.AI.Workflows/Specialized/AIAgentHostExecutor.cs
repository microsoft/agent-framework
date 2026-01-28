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

internal sealed class AIAgentHostExecutor : ChatProtocolExecutor
{
    private readonly AIAgent _agent;
    private readonly AIAgentHostOptions _options;
    private AgentSession? _session;
    private bool? _currentTurnEmitEvents;

    private AIContentExternalHandler<UserInputRequestContent, UserInputResponseContent>? _userInputHandler;
    private AIContentExternalHandler<FunctionCallContent, FunctionResultContent>? _functionCallHandler;

    private static readonly ChatProtocolExecutorOptions s_defaultChatProtocolOptions = new()
    {
        AutoSendTurnToken = false,
        StringMessageChatRole = ChatRole.User
    };

    public AIAgentHostExecutor(AIAgent agent, AIAgentHostOptions options) : base(id: agent.GetDescriptiveId(),
                                                                                 s_defaultChatProtocolOptions,
                                                                                 declareCrossRunShareable: false) // Explicitly false, because we maintain turn state on the instance
    {
        this._agent = agent;
        this._options = options;
    }

    private RouteBuilder ConfigureUserInputRoutes(RouteBuilder routeBuilder)
    {
        this._userInputHandler = new AIContentExternalHandler<UserInputRequestContent, UserInputResponseContent>(
            ref routeBuilder,
            portId: $"{this.Id}_UserInput",
            intercepted: this._options.InterceptUserInputRequests,
            handler: this.HandleUserInputResponseAsync);

        this._functionCallHandler = new AIContentExternalHandler<FunctionCallContent, FunctionResultContent>(
            ref routeBuilder,
            portId: $"{this.Id}_FunctionCall",
            intercepted: this._options.InterceptUnterminatedFunctionCalls,
            handler: this.HandleFunctionResultAsync);

        return routeBuilder;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        routeBuilder = base.ConfigureRoutes(routeBuilder);
        return this.ConfigureUserInputRoutes(routeBuilder);
    }

    private ValueTask HandleUserInputResponseAsync(
        UserInputResponseContent response,
        IWorkflowContext context,
        CancellationToken cancellationToken)
    {
        if (!this._userInputHandler!.MarkRequestAsHandled(response.Id))
        {
            throw new InvalidOperationException($"No pending UserInputRequest found with id '{response.Id}'.");
        }

        List<ChatMessage> implicitTurnMessages = [new ChatMessage(ChatRole.User, [response])];

        // ContinueTurnAsync owns failing to emit a TurnToken if this response does not clear up all remaining outstanding requests.
        return this.ContinueTurnAsync(implicitTurnMessages, context, this._currentTurnEmitEvents ?? false, cancellationToken);
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

        List<ChatMessage> implicitTurnMessages = [new ChatMessage(ChatRole.Tool, [result])];
        return this.ContinueTurnAsync(implicitTurnMessages, context, this._currentTurnEmitEvents ?? false, cancellationToken);
    }

    public bool ShouldEmitStreamingEvents(bool? emitEvents)
        => emitEvents ?? this._options.EmitAgentUpdateEvents ?? false;

    private async ValueTask<AgentSession> EnsureSessionAsync(IWorkflowContext context, CancellationToken cancellationToken) =>
        this._session ??= await this._agent.GetNewSessionAsync(cancellationToken).ConfigureAwait(false);

    private const string UserInputRequestStateKey = nameof(_userInputHandler);
    private const string FunctionCallRequestStateKey = nameof(_functionCallHandler);
    private const string AIAgentHostStateKey = nameof(AIAgentHostState);

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        AIAgentHostState state = new(this._session?.Serialize(), this._currentTurnEmitEvents);
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

        await context.SendMessageAsync(response.Messages is List<ChatMessage> list ? list : response.Messages.ToList(), cancellationToken)
                     .ConfigureAwait(false);

        // If we have no outstanding requests, we can yield a turn token back to the workflow.
        if (!this.HasOutstandingRequests)
        {
            await context.SendMessageAsync(new TurnToken(this._currentTurnEmitEvents), cancellationToken).ConfigureAwait(false);
            this._currentTurnEmitEvents = null; // Possibly not actually necessary, but cleaning this up makes it clearer when debugging
        }
    }

    protected override ValueTask TakeTurnAsync(List<ChatMessage> messages, IWorkflowContext context, bool? emitEvents, CancellationToken cancellationToken = default)
        => this.ContinueTurnAsync(messages, context, this.ShouldEmitStreamingEvents(emitEvents), cancellationToken);

    private async ValueTask<AgentResponse> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, bool emitEvents, CancellationToken cancellationToken = default)
    {
#pragma warning disable MEAI001
        Dictionary<string, UserInputRequestContent> userInputRequests = new();
        Dictionary<string, FunctionCallContent> functionCalls = new();
        AgentResponse response;

        if (emitEvents)
        {
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
            // Run the agent in streaming mode only when agent run update events are to be emitted.
            IAsyncEnumerable<AgentResponseUpdate> agentStream = this._agent.RunStreamingAsync(
                messages,
                await this.EnsureSessionAsync(context, cancellationToken).ConfigureAwait(false),
                cancellationToken: cancellationToken);

            List<AgentResponseUpdate> updates = [];
            await foreach (AgentResponseUpdate update in agentStream.ConfigureAwait(false))
            {
                await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
                ExtractUnservicedRequests(update.Contents);
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

            ExtractUnservicedRequests(response.Messages.SelectMany(message => message.Contents));
        }

        if (this._options.EmitAgentResponseEvents == true)
        {
            await context.YieldOutputAsync(response, cancellationToken).ConfigureAwait(false);
        }

        if (userInputRequests.Count > 0 || functionCalls.Count > 0)
        {
            Task userInputTask = this._userInputHandler?.ProcessRequestContentsAsync(userInputRequests, context, cancellationToken) ?? Task.CompletedTask;
            Task functionCallTask = this._functionCallHandler?.ProcessRequestContentsAsync(functionCalls, context, cancellationToken) ?? Task.CompletedTask;

            await Task.WhenAll(userInputTask, functionCallTask)
                      .ConfigureAwait(false);
        }

        return response;

        void ExtractUnservicedRequests(IEnumerable<AIContent> contents)
        {
            foreach (AIContent content in contents)
            {
                if (content is UserInputRequestContent userInputRequest)
                {
                    // It is an error to simultaneously have multiple outstanding user input requests with the same ID.
                    userInputRequests.Add(userInputRequest.Id, userInputRequest);
                }
                else if (content is UserInputResponseContent userInputResponse)
                {
                    // If the set of messages somehow already has a corresponding user input response, remove it.
                    _ = userInputRequests.Remove(userInputResponse.Id);
                }
                else if (content is FunctionCallContent functionCall)
                {
                    // For function calls, we emit an event to notify the workflow.
                    //
                    // possibility 1: this will be handled inline by the agent abstraction
                    // possibility 2: this will not be handled inline by the agent abstraction
                    functionCalls.Add(functionCall.CallId, functionCall);
                }
                else if (content is FunctionResultContent functionResult)
                {
                    _ = functionCalls.Remove(functionResult.CallId);
                }
            }
        }
#pragma warning restore MEAI001
    }
}
