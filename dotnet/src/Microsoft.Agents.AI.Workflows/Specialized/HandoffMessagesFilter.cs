// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

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

    public IEnumerable<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
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
