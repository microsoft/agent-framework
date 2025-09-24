﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

internal sealed class WorkflowMessageStore : ChatMessageStore
{
    private int _bookmark;
    private readonly List<ChatMessage> _chatMessages = [];

    public WorkflowMessageStore()
    {
    }

    public WorkflowMessageStore(JsonElement serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedStoreState.ValueKind is not JsonValueKind.Object)
        {
            throw new ArgumentException("The provided JsonElement must be a json object", nameof(serializedStoreState));
        }

        StoreState? state =
            serializedStoreState.Deserialize(
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState))) as StoreState;

        if (state?.Messages is not null)
        {
            this._chatMessages.AddRange(state.Messages);
        }

        this._bookmark = state?.Bookmark ?? 0;
    }

    internal sealed class StoreState
    {
        public int Bookmark { get; set; }
        public IList<ChatMessage> Messages { get; set; } = [];
    }

    internal void AddMessages(params IEnumerable<ChatMessage> messages) => this._chatMessages.AddRange(messages);

    public override Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken)
    {
        this._chatMessages.AddRange(messages);

        return Task.CompletedTask;
    }

    public override Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken) => Task.FromResult<IEnumerable<ChatMessage>>(this._chatMessages.AsReadOnly());

    public IEnumerable<ChatMessage> GetFromBookmark()
    {
        for (int i = this._bookmark; i < this._chatMessages.Count; i++)
        {
            yield return this._chatMessages[i];
        }
    }

    public void UpdateBookmark() => this._bookmark = this._chatMessages.Count;

    public override ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        StoreState state = new()
        {
            Bookmark = this._bookmark,
            Messages = this._chatMessages,
        };

        return new ValueTask<JsonElement?>
            (JsonSerializer.SerializeToElement(state,
            WorkflowsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState))));
    }
}
