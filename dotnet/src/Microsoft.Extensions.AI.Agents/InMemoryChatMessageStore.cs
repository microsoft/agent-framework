// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an in-memory store for chat messages associated with a specific thread.
/// </summary>
public class InMemoryChatMessageStore : List<ChatMessage>, IChatMessageStore
{
    /// <inheritdoc />
    public Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken)
    {
        if (messages is { Count: > 0 })
        {
            this.AddRange(messages);
        }

        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken)
    {
        return Task.FromResult<IEnumerable<ChatMessage>>(this);
    }

    /// <inheritdoc />
    public Task DeserializeAsync(JsonElement? stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (stateElement is null)
        {
            return Task.CompletedTask;
        }

        jsonSerializerOptions ??= AgentsJsonUtilities.DefaultOptions;

        var state = JsonSerializer.Deserialize(
            stateElement.Value,
            jsonSerializerOptions.GetTypeInfo(typeof(StoreState))) as StoreState;

        if (state?.Messages is { Count: > 0 } messages)
        {
            this.AddRange(messages);
        }

        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public Task<JsonElement?> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentsJsonUtilities.DefaultOptions;

        StoreState state = new()
        {
            Messages = this,
        };

        return Task.FromResult<JsonElement?>(JsonSerializer.SerializeToElement(state, jsonSerializerOptions.GetTypeInfo(typeof(StoreState))));
    }

    internal class StoreState
    {
        public IList<ChatMessage> Messages { get; set; } = new List<ChatMessage>();
    }
}
