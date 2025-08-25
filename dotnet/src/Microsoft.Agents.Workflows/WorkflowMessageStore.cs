// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

internal class WorkflowMessageStore : IChatMessageStore
{
    private int _bookmark = 0;
    private readonly List<ChatMessage> _chatMessages = new();

    internal class StoreState
    {
        public int Bookmark { get; set; }
        public IList<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
    }

    internal void AddMessages(params ChatMessage[] messages)
    {
        this._chatMessages.AddRange(messages);
    }

    public Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        this._chatMessages.AddRange(messages);

        return Task.CompletedTask;
    }

    public Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
    {
        return Task.FromResult<IEnumerable<ChatMessage>>(this._chatMessages.AsReadOnly());
    }

    public IEnumerable<ChatMessage> GetFromBookmark()
    {
        for (int i = this._bookmark; i < this._chatMessages.Count; i++)
        {
            yield return this._chatMessages[i];
        }
    }

    public void UpdateBookmark()
    {
        this._bookmark = this._chatMessages.Count;
    }

    public ValueTask DeserializeStateAsync(JsonElement? serializedStoreState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (serializedStoreState is null)
        {
            return default;
        }

        object? maybeState =
            JsonSerializer.Deserialize(
                serializedStoreState.Value,
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(StoreState)));

        if (maybeState is not StoreState state)
        {
            throw new JsonException("Invalid state format for WorkflowMessageStore.");
        }

        this._chatMessages.Clear();
        this._chatMessages.AddRange(state.Messages);

        this._bookmark = state.Bookmark;

        return default;
    }

    public ValueTask<JsonElement?> SerializeStateAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
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
