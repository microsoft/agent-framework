// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Extension methods for <see cref="AIProjectClient"/> to provide MemoryStores operations
/// using the SDK's HTTP pipeline until the SDK releases convenience methods.
/// </summary>
internal static class AIProjectClientExtensions
{
    /// <summary>
    /// Searches for relevant memories from a memory store based on conversation context.
    /// </summary>
    /// <param name="client">The AI Project client.</param>
    /// <param name="memoryStoreName">The name of the memory store to search.</param>
    /// <param name="scope">The namespace that logically groups and isolates memories, such as a user ID.</param>
    /// <param name="messages">The conversation messages to use for the search query.</param>
    /// <param name="maxMemories">Maximum number of memories to return.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Enumerable of memory content strings.</returns>
    public static async Task<IEnumerable<string>> SearchMemoriesAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int maxMemories,
        CancellationToken cancellationToken)
    {
        var request = new SearchMemoriesRequest
        {
            Scope = scope,
            Items = messages.ToArray(),
            Options = new SearchMemoriesOptions { MaxMemories = maxMemories }
        };

        var json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.SearchMemoriesRequest);
        var content = BinaryContent.Create(BinaryData.FromString(json));

        var requestOptions = new RequestOptions { CancellationToken = cancellationToken };
        ClientResult result = await client.MemoryStores.SearchMemoriesAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);

        var response = JsonSerializer.Deserialize(
            result.GetRawResponse().Content.ToString(),
            FoundryMemoryJsonContext.Default.SearchMemoriesResponse);

        return response?.Memories?.Select(m => m.MemoryItem?.Content ?? string.Empty)
            .Where(c => !string.IsNullOrWhiteSpace(c)) ?? [];
    }

    /// <summary>
    /// Updates memory store with conversation memories.
    /// </summary>
    /// <param name="client">The AI Project client.</param>
    /// <param name="memoryStoreName">The name of the memory store to update.</param>
    /// <param name="scope">The namespace that logically groups and isolates memories, such as a user ID.</param>
    /// <param name="messages">The conversation messages to extract memories from.</param>
    /// <param name="updateDelay">Delay in seconds before processing the update.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public static async Task UpdateMemoriesAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int updateDelay,
        CancellationToken cancellationToken)
    {
        var request = new UpdateMemoriesRequest
        {
            Scope = scope,
            Items = messages.ToArray(),
            UpdateDelay = updateDelay
        };

        var json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.UpdateMemoriesRequest);
        var content = BinaryContent.Create(BinaryData.FromString(json));

        var requestOptions = new RequestOptions { CancellationToken = cancellationToken };
        await client.MemoryStores.UpdateMemoriesAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);
    }

    /// <summary>
    /// Deletes all memories associated with a specific scope from a memory store.
    /// </summary>
    /// <param name="client">The AI Project client.</param>
    /// <param name="memoryStoreName">The name of the memory store.</param>
    /// <param name="scope">The namespace that logically groups and isolates memories to delete, such as a user ID.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    public static async Task DeleteScopeAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        CancellationToken cancellationToken)
    {
        var request = new DeleteScopeRequest { Scope = scope };

        var json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.DeleteScopeRequest);
        var content = BinaryContent.Create(BinaryData.FromString(json));

        var requestOptions = new RequestOptions { CancellationToken = cancellationToken };
        await client.MemoryStores.DeleteScopeAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);
    }
}
