// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows;

internal class MessageMerger
{
    private class ResponseMergeState(string? responseId)
    {
        public string? ResponseId { get; } = responseId;

        public Dictionary<string, List<AgentRunResponseUpdate>> UpdatesByMessageId { get; } = new();
        public List<AgentRunResponseUpdate> DanglingUpdates { get; } = new();

        public void AddUpdate(AgentRunResponseUpdate update)
        {
            if (update.MessageId is null)
            {
                this.DanglingUpdates.Add(update);
            }
            else
            {
                if (!this.UpdatesByMessageId.TryGetValue(update.MessageId, out List<AgentRunResponseUpdate>? updates))
                {
                    this.UpdatesByMessageId[update.MessageId] = updates = new List<AgentRunResponseUpdate>();
                }

                updates.Add(update);
            }
        }

        private AgentRunResponse ComputeResponse(List<AgentRunResponseUpdate> updates) => updates.ToAgentRunResponse();

        public AgentRunResponse ComputeMerged(string messageId)
        {
            if (this.UpdatesByMessageId.TryGetValue(Throw.IfNull(messageId), out List<AgentRunResponseUpdate>? updates))
            {
                return updates.ToAgentRunResponse();
            }

            throw new KeyNotFoundException($"No updates found for message ID '{messageId}' in response '{this.ResponseId}'.");
        }

        public AgentRunResponse ComputeDangling()
        {
            if (this.DanglingUpdates.Count == 0)
            {
                throw new InvalidOperationException("No dangling updates to compute a response from.");
            }

            return this.DanglingUpdates.ToAgentRunResponse();
        }

        public List<ChatMessage> ComputeFlattened()
        {
            List<ChatMessage> result = this.UpdatesByMessageId.Keys.Select(AggregateUpdatesToMessage)
                                                                   .ToList();

            result.AddRange(this.ComputeDangling().Messages);
            return result;

            ChatMessage AggregateUpdatesToMessage(string messageId)
            {
                List<AgentRunResponseUpdate> updates = this.UpdatesByMessageId[messageId];
                if (updates.Count == 0)
                {
                    throw new InvalidOperationException($"No updates found for message ID '{messageId}' in response '{this.ResponseId}'.");
                }

                return updates.Aggregate(null,
                    (ChatMessage? previous, AgentRunResponseUpdate current) =>
                    {
                        return previous == null
                             ? current.ToChatMessage()
                             : previous.UpdateWith(current);
                    })!;
            }
        }
    }

    private readonly Dictionary<string, ResponseMergeState> _mergeStates = new();
    private readonly ResponseMergeState _danglingState = new(null);

    public void AddUpdate(AgentRunResponseUpdate update)
    {
        if (update.ResponseId is null)
        {
            this._danglingState.DanglingUpdates.Add(update);
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

    private int CompareByDateTimeOffset(AgentRunResponse left, AgentRunResponse right)
    {
        const int LESS = -1, EQ = 0, GREATER = 1;

        if (left.CreatedAt == right.CreatedAt)
        {
            return EQ;
        }

        if (!left.CreatedAt.HasValue)
        {
            return GREATER;
        }

        if (!right.CreatedAt.HasValue)
        {
            return LESS;
        }

        return left.CreatedAt.Value.CompareTo(right.CreatedAt.Value);
    }

    public AgentRunResponse ComputeMerged(string primaryResponseId)
    {
        List<ChatMessage> messages = [];
        Dictionary<string, AgentRunResponse> responses = new();

        foreach (string responseId in this._mergeStates.Keys)
        {
            ResponseMergeState mergeState = this._mergeStates[responseId];

            List<AgentRunResponse> responseList = mergeState.UpdatesByMessageId.Keys.Select(messageId => mergeState.ComputeMerged(messageId)).ToList();
            if (mergeState.DanglingUpdates.Count > 0)
            {
                responseList.Add(mergeState.ComputeDangling());
            }

            responseList.Sort(this.CompareByDateTimeOffset);
            responses[responseId] = responseList.Aggregate(MergeResponses);
            messages.AddRange(responses[responseId].Messages);
        }

        messages.AddRange(this._danglingState.ComputeFlattened());
        return new AgentRunResponse(messages)
        {
            ResponseId = primaryResponseId,
        };

        AgentRunResponse MergeResponses(AgentRunResponse? current, AgentRunResponse incoming)
        {
            if (current is null)
            {
                return incoming;
            }

            if (current.ResponseId != incoming.ResponseId)
            {
                throw new InvalidOperationException($"Cannot merge responses with different IDs: '{current.ResponseId}' and '{incoming.ResponseId}'.");
            }

            List<object?> rawRepresentation = current.RawRepresentation as List<object?> ?? [];
            rawRepresentation.Add(incoming.RawRepresentation);

            return new()
            {
                AgentId = incoming.AgentId ?? current.AgentId,
                AdditionalProperties = incoming.AdditionalProperties ?? current.AdditionalProperties,
                CreatedAt = incoming.CreatedAt ?? current.CreatedAt,
                Messages = current.Messages.Concat(incoming.Messages).ToList(),
                ResponseId = current.ResponseId,
                RawRepresentation = rawRepresentation,
                Usage = Merge(current.Usage, incoming.Usage),
            };
        }

        static UsageDetails? Merge(UsageDetails? current, UsageDetails? incoming)
        {
            if (current == null)
            {
                return incoming;
            }

            AdditionalPropertiesDictionary<long>? additionalCounts = current.AdditionalCounts;
            if (incoming == null)
            {
                return current;
            }

            if (additionalCounts == null)
            {
                additionalCounts = incoming.AdditionalCounts;
            }
            else if (incoming.AdditionalCounts != null)
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
