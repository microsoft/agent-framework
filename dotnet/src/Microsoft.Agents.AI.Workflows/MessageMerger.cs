// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class MessageMerger
{
    private sealed class ResponseMergeState(string? responseId)
    {
        public string? ResponseId { get; } = responseId;

        // All updates for this response in streamed/arrival order. Grouping updates into messages is
        // delegated to M.E.AI (ToAgentResponse), which coalesces contiguous updates by message id
        // exactly like a directly-invoked agent - including merging an id-less update (e.g. a reasoning
        // summary that streams without a message id) with the text that follows it. Doing the grouping
        // here (bucketing per message id and appending id-less updates last) split a single assistant
        // message into two and reordered its content.
        private readonly List<AgentResponseUpdate> _updates = [];

        public bool HasUpdates => this._updates.Count > 0;

        public void AddUpdate(AgentResponseUpdate update) => this._updates.Add(update);

        public AgentResponse ComputeResponse() => this._updates.ToAgentResponse();

        public List<ChatMessage> ComputeFlattened() => this._updates.ToAgentResponse().Messages.ToList();
    }

    private readonly Dictionary<string, ResponseMergeState> _mergeStates = [];
    private readonly ResponseMergeState _danglingState = new(null);

    public void AddUpdate(AgentResponseUpdate update)
    {
        if (update.ResponseId is null)
        {
            this._danglingState.AddUpdate(update);
        }
        else
        {
            if (!this._mergeStates.TryGetValue(update.ResponseId, out ResponseMergeState? state))
            {
                this._mergeStates[update.ResponseId] = state = new ResponseMergeState(update.ResponseId);
            }

            state.AddUpdate(update);
        }
    }

    public AgentResponse ComputeMerged(string primaryResponseId, string? primaryAgentId = null, string? primaryAgentName = null)
    {
        List<ChatMessage> messages = [];
        Dictionary<string, AgentResponse> responses = [];
        HashSet<string> agentIds = [];
        HashSet<ChatFinishReason> finishReasons = [];

        foreach (string responseId in this._mergeStates.Keys)
        {
            ResponseMergeState mergeState = this._mergeStates[responseId];

            // Delegate update-to-message grouping to M.E.AI, which coalesces contiguous updates by
            // message id exactly like a directly-invoked agent. This keeps reasoning content that
            // streams without a message id in the same assistant message as the text that follows
            // it, preserving both content order and the single-message structure.
            responses[responseId] = mergeState.ComputeResponse();
            messages.AddRange(GetMessagesWithCreatedAt(responses[responseId]));
        }

        UsageDetails? usage = null;
        AdditionalPropertiesDictionary? additionalProperties = null;
        HashSet<DateTimeOffset> createdTimes = [];

        foreach (AgentResponse response in responses.Values)
        {
            if (response.AgentId is not null)
            {
                agentIds.Add(response.AgentId);
            }

            if (response.CreatedAt.HasValue)
            {
                createdTimes.Add(response.CreatedAt.Value);
            }

            if (response.FinishReason.HasValue)
            {
                finishReasons.Add(response.FinishReason.Value);
            }

            usage = MergeUsage(usage, response.Usage);
            additionalProperties = MergeProperties(additionalProperties, response.AdditionalProperties);
        }

        if (this._danglingState.HasUpdates)
        {
            messages.AddRange(this._danglingState.ComputeFlattened());
        }

        // Remove any empty text contents or messages that are now empty.
        foreach (var m in messages)
        {
            for (int i = m.Contents.Count - 1; i >= 0; i--)
            {
                if (m.Contents[i] is TextContent textContent &&
                    string.IsNullOrWhiteSpace(textContent.Text))
                {
                    m.Contents.RemoveAt(i);
                }
            }
        }

        messages.RemoveAll(m => m.Contents.Count == 0);

        return new AgentResponse(messages)
        {
            ResponseId = primaryResponseId,
            AgentId = primaryAgentId
                   ?? primaryAgentName
                   ?? (agentIds.Count == 1 ? agentIds.First() : null),
            FinishReason = finishReasons.Count == 1 ? finishReasons.First() : null,
            CreatedAt = DateTimeOffset.UtcNow,
            Usage = usage,
            AdditionalProperties = additionalProperties
        };

        static IEnumerable<ChatMessage> GetMessagesWithCreatedAt(AgentResponse response)
        {
            if (response.Messages.Count == 0)
            {
                return [];
            }

            if (response.CreatedAt is null)
            {
                return response.Messages;
            }

            DateTimeOffset? createdAt = response.CreatedAt;
            return response.Messages.Select(
                message => new ChatMessage
                {
                    Role = message.Role,
                    AuthorName = message.AuthorName,
                    Contents = message.Contents,
                    MessageId = message.MessageId,
                    CreatedAt = createdAt,
                    RawRepresentation = message.RawRepresentation
                });
        }

        static AdditionalPropertiesDictionary? MergeProperties(AdditionalPropertiesDictionary? current, AdditionalPropertiesDictionary? incoming)
        {
            if (current is null)
            {
                return incoming;
            }

            if (incoming is null)
            {
                return current;
            }

            AdditionalPropertiesDictionary merged = new(current);
            foreach (string key in incoming.Keys)
            {
                merged[key] = incoming[key];
            }

            return merged;
        }

        static UsageDetails? MergeUsage(UsageDetails? current, UsageDetails? incoming)
        {
            if (current is null)
            {
                return incoming;
            }

            AdditionalPropertiesDictionary<long>? additionalCounts = current.AdditionalCounts;
            if (incoming is null)
            {
                return current;
            }

            if (additionalCounts is null)
            {
                additionalCounts = incoming.AdditionalCounts;
            }
            else if (incoming.AdditionalCounts is not null)
            {
                foreach (string key in incoming.AdditionalCounts.Keys)
                {
                    additionalCounts[key] = incoming.AdditionalCounts[key] +
                                            (additionalCounts.TryGetValue(key, out long? existingCount) ? existingCount.Value : 0);
                }
            }

            return new UsageDetails
            {
                InputTokenCount = current.InputTokenCount + incoming.InputTokenCount,
                OutputTokenCount = current.OutputTokenCount + incoming.OutputTokenCount,
                TotalTokenCount = current.TotalTokenCount + incoming.TotalTokenCount,
                AdditionalCounts = additionalCounts,
            };
        }
    }
}
