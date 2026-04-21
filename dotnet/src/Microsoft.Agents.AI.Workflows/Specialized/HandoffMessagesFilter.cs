// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
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

        HashSet<string> filteredCallsWithoutResponses = new();
        List<ChatMessage> retainedMessages = [];

        bool filterAllToolCalls = this._filteringBehavior == HandoffToolCallFilteringBehavior.All;

        // The logic of filtering is fairly straightforward: We are only interested in FunctionCallContent and FunctionResponseContent.
        // We are going to assume that Handoff operates as follows:
        //  * Each agent is only taking one turn at a time
        //  * Each agent is taking a turn alone
        //
        // In the case of certain providers, like Gemini (see microsoft/agent-framework #5244), we will see the function call name as the
        // call id as well, so we may see multiple calls with the same call id, and assume that the call is terminated before another
        // "CallId-less" FCC is issued. We also need to rely on the idea that FRC follows their corresponding FCC in the message stream.
        // (This changes the previous behaviour where FRC could arrive earlier, and relies on strict ordering).
        //
        // The benefit of expecting all the AIContent to be strictly ordered is that we never need to reach back into a post-filtered
        // content to retroactively remove it, or to try to inject it back into the middle of a Message that has already been processed.

        foreach (ChatMessage unfilteredMessage in messages)
        {
            if (unfilteredMessage.Contents is null || unfilteredMessage.Contents.Count == 0)
            {
                retainedMessages.Add(unfilteredMessage);
                continue;
            }

            // We may need to filter out a subset of the message's content, but we won't know until we iterate through it. Create a new list
            // of AIContent which we will stuff into a clone of the message if we need to filter out any content.
            List<AIContent> retainedContents = new(capacity: unfilteredMessage.Contents.Count);

            foreach (AIContent content in unfilteredMessage.Contents)
            {
                if (content is FunctionCallContent fcc
                    && (filterAllToolCalls || IsHandoffFunctionName(fcc.Name)))
                {
                    // If we already have an unmatched candidate with the same CallId, that means we have two FCCs in a row without an FRC,
                    // which violates our assumption of strict ordering.
                    if (!filteredCallsWithoutResponses.Add(fcc.CallId))
                    {
                        throw new InvalidOperationException($"Duplicate FunctionCallContent with CallId '{fcc.CallId}' without corresponding FunctionResultContent.");
                    }

                    // If we are filtering all tool calls, or this is a handoff call (and we are not filtering None, already checked), then
                    // filter this FCC
                    continue;
                }
                else if (content is FunctionResultContent frc)
                {
                    // We rely on the corresponding FCC to have already been processed, so check if it is in the candidate dictionary.
                    // If it is, we can filter out the FRC, but we need to remove the candidate from the dictionary, since a future FCC can
                    // come in with the same CallId, and should be considered a new call that may need to be filtered.
                    if (filteredCallsWithoutResponses.Remove(frc.CallId))
                    {
                        continue;
                    }
                }

                // FCC/FRC, but not filtered, or neither FCC nor FRC: this should not be filtered out
                retainedContents.Add(content);
            }

            if (retainedContents.Count == 0)
            {
                // message was fully filtered, skip it
                continue;
            }

            ChatMessage filteredMessage = unfilteredMessage.Clone();
            filteredMessage.Contents = retainedContents;
            retainedMessages.Add(filteredMessage);
        }

        return retainedMessages;
    }
}
