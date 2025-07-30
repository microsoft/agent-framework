// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an in-memory store for chat messages associated with a specific thread.
/// </summary>
public class InMemoryChatMessageStore : List<ChatMessage>, IChatMessageStore
{
    /// <inheritdoc />
    public Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        _ = Throw.IfNull(messages);
        this.AddRange(messages);
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
    {
        return Task.FromResult<IEnumerable<ChatMessage>>(this);
    }

    /// <inheritdoc />
    public ValueTask DeserializeAsync(JsonElement? serializedThread, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (serializedThread is null)
        {
            return new ValueTask();
        }

        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        var state = JsonSerializer.Deserialize(
            serializedThread.Value,
            jsonSerializerOptions.GetTypeInfo(typeof(StoreState))) as StoreState;

        if (state?.Messages is { Count: > 0 } messages)
        {
            this.AddRange(messages);
        }

        return new ValueTask();
    }

    /// <inheritdoc />
    public ValueTask<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        StoreState state = new()
        {
            Messages = this,
        };

        return new ValueTask<JsonElement?>(JsonSerializer.SerializeToElement(state, jsonSerializerOptions.GetTypeInfo(typeof(StoreState))));
    }

    internal class StoreState
    {
        public IList<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
    }
}
