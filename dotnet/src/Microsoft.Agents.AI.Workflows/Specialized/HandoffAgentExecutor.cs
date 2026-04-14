// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
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

[Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
internal sealed class HandoffMessagesFilter
{
    private readonly HandoffToolCallFilteringBehavior _filteringBehavior;

    public HandoffMessagesFilter(HandoffToolCallFilteringBehavior filteringBehavior)
    {
        this._filteringBehavior = filteringBehavior;
    }

    [Experimental(DiagnosticConstants.ExperimentalFeatureDiagnostic)]
    internal static bool IsHandoffFunctionName(string name)
    {
        return name.StartsWith(HandoffWorkflowBuilder.FunctionPrefix, StringComparison.Ordinal);
    }

    public IEnumerable<ChatMessage> FilterMessages(List<ChatMessage> messages)
    {
        if (this._filteringBehavior == HandoffToolCallFilteringBehavior.None)
        {
            return messages;
        }

        Dictionary<string, FilterCandidateState> filteringCandidates = new();
        List<ChatMessage> filteredMessages = [];
        HashSet<int> messagesToRemove = [];

        bool filterHandoffOnly = this._filteringBehavior == HandoffToolCallFilteringBehavior.HandoffOnly;
        foreach (ChatMessage unfilteredMessage in messages)
        {
            ChatMessage filteredMessage = unfilteredMessage.Clone();

            // .Clone() is shallow, so we cannot modify the contents of the cloned message in place.
            List<AIContent> contents = [];
            contents.Capacity = unfilteredMessage.Contents?.Count ?? 0;
            filteredMessage.Contents = contents;

            // Because this runs after the role changes from assistant to user for the target agent, we cannot rely on tool calls
            // originating only from messages with the Assistant role. Instead, we need to inspect the contents of all non-Tool (result)
            // FunctionCallContent.
            if (unfilteredMessage.Role != ChatRole.Tool)
            {
                for (int i = 0; i < unfilteredMessage.Contents!.Count; i++)
                {
                    AIContent content = unfilteredMessage.Contents[i];
                    if (content is not FunctionCallContent fcc || (filterHandoffOnly && !IsHandoffFunctionName(fcc.Name)))
                    {
                        filteredMessage.Contents.Add(content);

                        // Track non-handoff function calls so their tool results are preserved in HandoffOnly mode
                        if (filterHandoffOnly && content is FunctionCallContent nonHandoffFcc)
                        {
                            filteringCandidates[nonHandoffFcc.CallId] = new FilterCandidateState(nonHandoffFcc.CallId)
                            {
                                IsHandoffFunction = false,
                            };
                        }
                    }
                    else if (filterHandoffOnly)
                    {
                        if (!filteringCandidates.TryGetValue(fcc.CallId, out FilterCandidateState? candidateState))
                        {
                            filteringCandidates[fcc.CallId] = new FilterCandidateState(fcc.CallId)
                            {
                                IsHandoffFunction = true,
                            };
                        }
                        else
                        {
                            candidateState.IsHandoffFunction = true;
                            (int messageIndex, int contentIndex) = candidateState.FunctionCallResultLocation!.Value;
                            ChatMessage messageToFilter = filteredMessages[messageIndex];
                            messageToFilter.Contents.RemoveAt(contentIndex);
                            if (messageToFilter.Contents.Count == 0)
                            {
                                messagesToRemove.Add(messageIndex);
                            }
                        }
                    }
                    else
                    {
                        // All mode: strip all FunctionCallContent
                    }
                }
            }
            else
            {
                if (!filterHandoffOnly)
                {
                    continue;
                }

                for (int i = 0; i < unfilteredMessage.Contents!.Count; i++)
                {
                    AIContent content = unfilteredMessage.Contents[i];
                    if (content is not FunctionResultContent frc
                        || (filteringCandidates.TryGetValue(frc.CallId, out FilterCandidateState? candidateState)
                            && candidateState.IsHandoffFunction is false))
                    {
                        // Either this is not a function result content, so we should let it through, or it is a FRC that
                        // we know is not related to a handoff call. In either case, we should include it.
                        filteredMessage.Contents.Add(content);
                    }
                    else if (candidateState is null)
                    {
                        // We haven't seen the corresponding function call yet, so add it as a candidate to be filtered later
                        filteringCandidates[frc.CallId] = new FilterCandidateState(frc.CallId)
                        {
                            FunctionCallResultLocation = (filteredMessages.Count, filteredMessage.Contents.Count),
                        };
                    }
                    // else we have seen the corresponding function call and it is a handoff, so we should filter it out.
                }
            }

            if (filteredMessage.Contents.Count > 0)
            {
                filteredMessages.Add(filteredMessage);
            }
        }

        return filteredMessages.Where((_, index) => !messagesToRemove.Contains(index));
    }

    private class FilterCandidateState(string callId)
    {
        public (int MessageIndex, int ContentIndex)? FunctionCallResultLocation { get; set; }

        public string CallId => callId;

        public bool? IsHandoffFunction { get; set; }
    }
}

internal struct AgentInvocationResult(AgentResponse agentResponse, string? handoffTargetId)
{
    public AgentResponse Response => agentResponse;

    public string? HandoffTargetId => handoffTargetId;

    [MemberNotNullWhen(true, nameof(HandoffTargetId))]
    public bool IsHandoffRequested => this.HandoffTargetId != null;
}

internal record HandoffAgentHostState(HandoffState? CurrentTurnState, List<ChatMessage> FilteredIncomingMessages, List<ChatMessage> TurnMessages)
{
    public HandoffState PrepareHandoff(AgentInvocationResult invocationResult, string currentAgentId)
    {
        if (this.CurrentTurnState == null)
        {
            throw new InvalidOperationException("Cannot create a handoff request: Out of turn.");
        }

        IEnumerable<ChatMessage> allMessages = [.. this.CurrentTurnState.Messages, .. this.TurnMessages, .. invocationResult.Response.Messages];

        return new(this.CurrentTurnState.TurnToken, invocationResult.HandoffTargetId, allMessages.ToList(), currentAgentId);
    }
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

    private static HandoffAgentHostState InitialStateFactory() => new(null, [], []);

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
            state.TurnMessages.Add(new ChatMessage(ChatRole.User, [response])
            {
                CreatedAt = DateTimeOffset.UtcNow,
                MessageId = Guid.NewGuid().ToString("N"),
            });

            return this.ContinueTurnAsync(state, ctx, ct);
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
            state.TurnMessages.Add(
                new ChatMessage(ChatRole.Tool, [result])
                {
                    AuthorName = this._agent.Name ?? this._agent.Id,
                    CreatedAt = DateTimeOffset.UtcNow,
                    MessageId = Guid.NewGuid().ToString("N"),
                });

            return this.ContinueTurnAsync(state, ctx, ct);
        }, context, skipCache: false, cancellationToken);
    }

    private async ValueTask<HandoffAgentHostState?> ContinueTurnAsync(HandoffAgentHostState state, IWorkflowContext context, CancellationToken cancellationToken)
    {
        List<ChatMessage>? roleChanges = state.FilteredIncomingMessages.ChangeAssistantToUserForOtherParticipants(this._agent.Name ?? this._agent.Id);

        bool emitUpdateEvents = state.CurrentTurnState!.ShouldEmitStreamingEvents(this._options.EmitAgentResponseUpdateEvents);
        AgentInvocationResult result = await this.InvokeAgentAsync([.. state.FilteredIncomingMessages, .. state.TurnMessages], context, emitUpdateEvents, cancellationToken)
                                                     .ConfigureAwait(false);

        if (this.HasOutstandingRequests && result.IsHandoffRequested)
        {
            throw new InvalidOperationException("Cannot request a handoff while holding pending requests.");
        }

        roleChanges.ResetUserToAssistantForChangedRoles();

        // We send on the HandoffState even if handoff is not requested because we might be terminating the processing, but this only
        // happens if we have no outstanding requests.
        if (!this.HasOutstandingRequests)
        {
            HandoffState outgoingState = state.PrepareHandoff(result, this._agent.Id);

            await context.SendMessageAsync(outgoingState, cancellationToken).ConfigureAwait(false);

            // reset the state for the next handoff (return-to-current is modeled as a new handoff turn, as opposed to "HITL", which
            // can be a bit confusing.)
            return null;
        }

        state.TurnMessages.AddRange(result.Response.Messages);
        return state;
    }

    public override ValueTask HandleAsync(HandoffState message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        return this.InvokeWithStateAsync(InvokeContinueTurnAsync, context, skipCache: false, cancellationToken);

        ValueTask<HandoffAgentHostState?> InvokeContinueTurnAsync(HandoffAgentHostState state, IWorkflowContext context, CancellationToken cancellationToken)
        {
            // Check that we are not getting this message while in the middle of a turn
            if (state.CurrentTurnState != null)
            {
                throw new InvalidOperationException("Cannot have multiple simultaneous conversations in Handoff Orchestration.");
            }

            // If a handoff was invoked by a previous agent, filter out the handoff function
            // call and tool result messages before sending to the underlying agent. These
            // are internal workflow mechanics that confuse the target model into ignoring the
            // original user question.
            HandoffMessagesFilter handoffMessagesFilter = new(this._options.ToolCallFilteringBehavior);
            IEnumerable<ChatMessage> messagesForAgent = message.RequestedHandoffTargetAgentId is not null
                ? handoffMessagesFilter.FilterMessages(message.Messages)
                : message.Messages;

            // This works because the runtime guarantees that a given executor instance will process messages serially,
            // though there is no global cross-executor ordering guarantee (and in turn, no canonical message delivery order)
            state = new(message, messagesForAgent.ToList(), []);

            return this.ContinueTurnAsync(state, context, cancellationToken);
        }
    }

    private const string UserInputRequestStateKey = nameof(_userInputHandler);
    private const string FunctionCallRequestStateKey = nameof(_functionCallHandler);

    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task userInputRequestsTask = this._userInputHandler?.OnCheckpointingAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRequestsTask = this._functionCallHandler?.OnCheckpointingAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;

        Task baseTask = base.OnCheckpointingAsync(context, cancellationToken).AsTask();
        await Task.WhenAll(userInputRequestsTask, functionCallRequestsTask, baseTask).ConfigureAwait(false);
    }

    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Task userInputRestoreTask = this._userInputHandler?.OnCheckpointRestoredAsync(UserInputRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;
        Task functionCallRestoreTask = this._functionCallHandler?.OnCheckpointRestoredAsync(FunctionCallRequestStateKey, context, cancellationToken).AsTask() ?? Task.CompletedTask;

        await Task.WhenAll(userInputRestoreTask, functionCallRestoreTask).ConfigureAwait(false);
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);
    }
    private bool HasOutstandingRequests => (this._userInputHandler?.HasPendingRequests == true)
                                        || (this._functionCallHandler?.HasPendingRequests == true);

    private async ValueTask<AgentInvocationResult> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, bool emitUpdateEvents, CancellationToken cancellationToken = default)
    {
        AgentResponse response;

        AIAgentUnservicedRequestsCollector collector = new(this._userInputHandler, this._functionCallHandler);

        IAsyncEnumerable<AgentResponseUpdate> agentStream = this._agent.RunStreamingAsync(
                messages,
                options: this._agentOptions,
                cancellationToken: cancellationToken);

        string? requestedHandoff = null;
        List<AgentResponseUpdate> updates = [];
        List<FunctionCallContent> candidateRequests = [];
        await foreach (AgentResponseUpdate update in agentStream.ConfigureAwait(false))
        {
            await AddUpdateAsync(update, cancellationToken).ConfigureAwait(false);

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
