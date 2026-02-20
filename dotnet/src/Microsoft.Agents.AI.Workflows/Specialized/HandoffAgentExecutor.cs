// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class HandoffAgentExecutorOptions
{
    public HandoffAgentExecutorOptions(string? handoffInstructions, HandoffToolCallFilteringBehavior toolCallFilteringBehavior)
    {
        this.HandoffInstructions = handoffInstructions;
        this.ToolCallFilteringBehavior = toolCallFilteringBehavior;
    }

    public string? HandoffInstructions { get; set; }

    public HandoffToolCallFilteringBehavior ToolCallFilteringBehavior { get; set; } = HandoffToolCallFilteringBehavior.HandoffOnly;
}

internal sealed class HandoffMessagesFilter
{
    private readonly HandoffToolCallFilteringBehavior _filteringBehavior;

    public HandoffMessagesFilter(HandoffToolCallFilteringBehavior filteringBehavior)
    {
        this._filteringBehavior = filteringBehavior;
    }

    internal static bool IsHandoffFunctionName(string name)
    {
        return name.StartsWith(HandoffsWorkflowBuilder.FunctionPrefix, StringComparison.Ordinal);
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

/// <summary>Executor used to represent an agent in a handoffs workflow, responding to <see cref="HandoffState"/> events.</summary>
internal sealed class HandoffAgentExecutor(
    AIAgent agent,
    HandoffAgentExecutorOptions options) : Executor<HandoffState, HandoffState>(agent.GetDescriptiveId(), declareCrossRunShareable: true), IResettableExecutor
{
    private static readonly JsonElement s_handoffSchema = AIFunctionFactory.Create(
        ([Description("The reason for the handoff")] string? reasonForHandoff) => { }).JsonSchema;

    private readonly AIAgent _agent = agent;
    private readonly HashSet<string> _handoffFunctionNames = [];
    private ChatClientAgentRunOptions? _agentOptions;

    public void Initialize(
        WorkflowBuilder builder,
        Executor end,
        Dictionary<string, HandoffAgentExecutor> executors,
        HashSet<HandoffTarget> handoffs) =>
        builder.AddSwitch(this, sb =>
        {
            if (handoffs.Count != 0)
            {
                Debug.Assert(this._agentOptions is null);
                this._agentOptions = new()
                {
                    ChatOptions = new()
                    {
                        AllowMultipleToolCalls = false,
                        Instructions = options.HandoffInstructions,
                        Tools = [],
                    },
                };

                int index = 0;
                foreach (HandoffTarget handoff in handoffs)
                {
                    index++;
                    var handoffFunc = AIFunctionFactory.CreateDeclaration($"{HandoffsWorkflowBuilder.FunctionPrefix}{index}", handoff.Reason, s_handoffSchema);

                    this._handoffFunctionNames.Add(handoffFunc.Name);

                    this._agentOptions.ChatOptions.Tools.Add(handoffFunc);

                    sb.AddCase<HandoffState>(state => state?.InvokedHandoff == handoffFunc.Name, executors[handoff.Target.Id]);
                }
            }

            sb.WithDefault(end);
        });

    public override async ValueTask<HandoffState> HandleAsync(HandoffState message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        string? requestedHandoff = null;
        List<AgentResponseUpdate> updates = [];
        List<ChatMessage> allMessages = message.Messages;

        List<ChatMessage>? roleChanges = allMessages.ChangeAssistantToUserForOtherParticipants(this._agent.Name ?? this._agent.Id);

        // If a handoff was invoked by a previous agent, filter out the handoff function
        // call and tool result messages before sending to the underlying agent. These
        // are internal workflow mechanics that confuse the target model into ignoring the
        // original user question.
        HandoffMessagesFilter handoffMessagesFilter = new(options.ToolCallFilteringBehavior);
        IEnumerable<ChatMessage> messagesForAgent = message.InvokedHandoff is not null
            ? handoffMessagesFilter.FilterMessages(allMessages)
            : allMessages;

        await foreach (var update in this._agent.RunStreamingAsync(messagesForAgent,
                                                                   options: this._agentOptions,
                                                                   cancellationToken: cancellationToken)
                                                .ConfigureAwait(false))
        {
            await AddUpdateAsync(update, cancellationToken).ConfigureAwait(false);

            foreach (var fcc in update.Contents.OfType<FunctionCallContent>()
                                               .Where(fcc => this._handoffFunctionNames.Contains(fcc.Name)))
            {
                requestedHandoff = fcc.Name;
                await AddUpdateAsync(
                        new AgentResponseUpdate
                        {
                            AgentId = this._agent.Id,
                            AuthorName = this._agent.Name ?? this._agent.Id,
                            Contents = [new FunctionResultContent(fcc.CallId, "Transferred.")],
                            CreatedAt = DateTimeOffset.UtcNow,
                            MessageId = Guid.NewGuid().ToString("N"),
                            Role = ChatRole.Tool,
                        },
                        cancellationToken
                     )
                    .ConfigureAwait(false);
            }
        }

        allMessages.AddRange(updates.ToAgentResponse().Messages);

        roleChanges.ResetUserToAssistantForChangedRoles();

        return new(message.TurnToken, requestedHandoff, allMessages);

        async Task AddUpdateAsync(AgentResponseUpdate update, CancellationToken cancellationToken)
        {
            updates.Add(update);
            if (message.TurnToken.EmitEvents is true)
            {
                await context.YieldOutputAsync(update, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    public ValueTask ResetAsync() => default;
}
