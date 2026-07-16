// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

internal sealed class MessageMerger
{
    private sealed class MessageMergeState(string? messageId)
    {
        public string? MessageId { get; } = messageId;

        public List<AgentResponseUpdate> Updates { get; } = [];

        // The role of the message is taken from its first update. Buckets always contain at least
        // one update by the time they are read.
        public ChatRole? Role => this.Updates.Count > 0 ? this.Updates[0].Role : null;
    }

    private sealed class ResponseMergeState(string? responseId)
    {
        private readonly Dictionary<string, MessageMergeState> _messageStates = [];
        private readonly List<MessageMergeState> _messageStatesInOrder = [];
        private MessageMergeState? _lastObservedState;

        public string? ResponseId { get; } = responseId;

        public void AddUpdate(AgentResponseUpdate update)
        {
            MessageMergeState state = this.GetOrCreateMessageState(update.MessageId);
            state.Updates.Add(update);
            this._lastObservedState = state;
        }

        private MessageMergeState GetOrCreateMessageState(string? messageId)
        {
            if (messageId is null)
            {
                if (this._lastObservedState is { MessageId: null })
                {
                    return this._lastObservedState;
                }

                MessageMergeState state = new(null);
                this._messageStatesInOrder.Add(state);
                return state;
            }

            if (!this._messageStates.TryGetValue(messageId, out MessageMergeState? existingState))
            {
                existingState = new(messageId);
                this._messageStates[messageId] = existingState;
                this._messageStatesInOrder.Add(existingState);
            }

            return existingState;
        }

        public List<AgentResponse> ComputeMerged()
        {
            // Message buckets keep their first-seen order. Grouping updates into messages is delegated
            // to M.E.AI (ToAgentResponse), which coalesces contiguous updates by message id exactly like
            // a directly-invoked agent. Folding an id-less segment (e.g. a streamed reasoning summary)
            // into the following id'd message of the same role is handled once, at the flattened-message
            // level in MessageMerger.ComputeMerged, so it works both within a single response bucket and
            // across buckets (see https://github.com/microsoft/agent-framework/issues/6329).
            List<MessageMergeState> ordered = this._messageStatesInOrder;
            List<AgentResponse> responses = new(ordered.Count);

            foreach (MessageMergeState current in ordered)
            {
                responses.Add(current.Updates.ToAgentResponse());
            }

            return responses;
        }

        public List<ChatMessage> ComputeFlattened()
            => this.ComputeMerged().SelectMany(response => response.Messages).ToList();
    }

    private readonly Dictionary<string, ResponseMergeState> _mergeStates = [];
    private readonly List<string> _responseIdsInOrder = [];
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
                this._responseIdsInOrder.Add(update.ResponseId);
            }

            state.AddUpdate(update);
        }
    }

    public AgentResponse ComputeMerged(string primaryResponseId, string? primaryAgentId = null, string? primaryAgentName = null)
    {
        List<ChatMessage> messages = [];
        List<AgentResponse> responses = [];
        HashSet<string> agentIds = [];
        HashSet<ChatFinishReason> finishReasons = [];

        foreach (string responseId in this._responseIdsInOrder)
        {
            ResponseMergeState mergeState = this._mergeStates[responseId];

            List<AgentResponse> responseList = mergeState.ComputeMerged();
            AgentResponse response = responseList.Aggregate(MergeResponses);
            responses.Add(response);
            messages.AddRange(GetMessagesWithCreatedAt(response));
        }

        UsageDetails? usage = null;
        AdditionalPropertiesDictionary? additionalProperties = null;

        foreach (AgentResponse response in responses)
        {
            if (response.AgentId is not null)
            {
                agentIds.Add(response.AgentId);
            }

            if (response.FinishReason.HasValue)
            {
                finishReasons.Add(response.FinishReason.Value);
            }

            usage = MergeUsage(usage, response.Usage);
            additionalProperties = MergeProperties(additionalProperties, response.AdditionalProperties);
        }

        messages.AddRange(this._danglingState.ComputeFlattened());

        // Fold an id-less message that is immediately followed by an id'd message of the same role
        // into that message. A streamed reasoning summary often arrives without a message id and, when
        // an agent is hosted inside a workflow, can land in a different response bucket than the answer
        // text that follows it. The per-response fold cannot merge across buckets, so we also fold here
        // at the flattened-message level to keep the reasoning and the answer in a single assistant
        // message (see https://github.com/microsoft/agent-framework/issues/6329).
        for (int i = 0; i < messages.Count - 1; i++)
        {
            ChatMessage current = messages[i];
            ChatMessage next = messages[i + 1];

            if (current.MessageId is null && next.MessageId is not null && current.Role == next.Role)
            {
                messages[i + 1] = new ChatMessage
                {
                    Role = next.Role,
                    AuthorName = next.AuthorName ?? current.AuthorName,
                    Contents = [.. current.Contents, .. next.Contents],
                    MessageId = next.MessageId,
                    CreatedAt = current.CreatedAt ?? next.CreatedAt,
                    RawRepresentation = next.RawRepresentation,
                    AdditionalProperties = next.AdditionalProperties,
                };
                messages.RemoveAt(i);
                i--;
            }
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

        static AgentResponse MergeResponses(AgentResponse? current, AgentResponse incoming)
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
                FinishReason = incoming.FinishReason ?? current.FinishReason,
                Messages = current.Messages.Concat(incoming.Messages).ToList(),
                ResponseId = current.ResponseId,
                RawRepresentation = rawRepresentation,
                Usage = MergeUsage(current.Usage, incoming.Usage),
            };
        }

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
                    CreatedAt = message.CreatedAt ?? createdAt,
                    RawRepresentation = message.RawRepresentation,
                    AdditionalProperties = message.AdditionalProperties
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
