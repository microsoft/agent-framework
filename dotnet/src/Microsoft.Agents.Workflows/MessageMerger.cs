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

            if (this.DanglingUpdates.Count > 0)
            {
                result.AddRange(this.ComputeDangling().Messages);
            }

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

    public AgentRunResponse ComputeMerged(string primaryResponseId, string? primaryAgentId = null, string? primaryAgentName = null)
    {
        List<ChatMessage> messages = [];
        Dictionary<string, AgentRunResponse> responses = new();
        HashSet<string> agentIds = new();

        foreach (string responseId in this._mergeStates.Keys)
        {
            ResponseMergeState mergeState = this._mergeStates[responseId];

            List<AgentRunResponse> responseList = mergeState.UpdatesByMessageId.Keys.Select(mergeState.ComputeMerged).ToList();
            if (mergeState.DanglingUpdates.Count > 0)
            {
                responseList.Add(mergeState.ComputeDangling());
            }

            responseList.Sort(this.CompareByDateTimeOffset);
            responses[responseId] = responseList.Aggregate(MergeResponses);
            messages.AddRange(GetMessagesWithCreatedAt(responses[responseId]));
        }

        UsageDetails? usage = null;
        AdditionalPropertiesDictionary? additionalProperties = null;
        HashSet<DateTimeOffset> createdTimes = new();

        foreach (AgentRunResponse response in responses.Values)
        {
            if (response.AgentId != null)
            {
                agentIds.Add(response.AgentId);
            }

            if (response.CreatedAt.HasValue)
            {
                createdTimes.Add(response.CreatedAt.Value);
            }

            usage = MergeUsage(usage, response.Usage);
            additionalProperties = MergeProperties(additionalProperties, response.AdditionalProperties);
        }

        messages.AddRange(this._danglingState.ComputeFlattened());
        return new AgentRunResponse(messages)
        {
            ResponseId = primaryResponseId,
            AgentId = primaryAgentId
                   ?? primaryAgentName
                   ?? (agentIds.Count == 1 ? agentIds.First() : null),
            CreatedAt = DateTimeOffset.Now,
            Usage = usage,
            AdditionalProperties = additionalProperties
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
                AdditionalProperties = MergeProperties(current.AdditionalProperties, incoming.AdditionalProperties),
                CreatedAt = incoming.CreatedAt ?? current.CreatedAt,
                Messages = current.Messages.Concat(incoming.Messages).ToList(),
                ResponseId = current.ResponseId,
                RawRepresentation = rawRepresentation,
                Usage = MergeUsage(current.Usage, incoming.Usage),
            };
        }

        static IEnumerable<ChatMessage> GetMessagesWithCreatedAt(AgentRunResponse response)
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
            if (current == null)
            {
                return incoming;
            }

            if (incoming == null)
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
