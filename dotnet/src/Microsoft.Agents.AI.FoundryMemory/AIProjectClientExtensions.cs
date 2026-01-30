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
/// Internal extension methods for <see cref="AIProjectClient"/> to provide MemoryStores operations
/// using the SDK's HTTP pipeline until the SDK releases convenience methods.
/// </summary>
internal static class AIProjectClientExtensions
{
    /// <summary>
    /// Creates a memory store if it doesn't already exist.
    /// </summary>
    internal static async Task<bool> CreateMemoryStoreIfNotExistsAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string? description,
        string chatModel,
        string embeddingModel,
        CancellationToken cancellationToken)
    {
        // First try to get the store to see if it exists
        try
        {
            RequestOptions requestOptions = new() { CancellationToken = cancellationToken };
            await client.MemoryStores.GetMemoryStoreAsync(memoryStoreName, requestOptions).ConfigureAwait(false);
            return false; // Store already exists
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Store doesn't exist, create it
        }

        CreateMemoryStoreRequest request = new()
        {
            Name = memoryStoreName,
            Description = description,
            Definition = new MemoryStoreDefinitionRequest
            {
                Kind = "default",
                ChatModel = chatModel,
                EmbeddingModel = embeddingModel
            }
        };

        string json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.CreateMemoryStoreRequest);
        BinaryContent content = BinaryContent.Create(BinaryData.FromString(json));

        RequestOptions createOptions = new() { CancellationToken = cancellationToken };
        await client.MemoryStores.CreateMemoryStoreAsync(content, createOptions).ConfigureAwait(false);
        return true;
    }

    /// <summary>
    /// Searches for relevant memories from a memory store based on conversation context.
    /// </summary>
    internal static async Task<SearchMemoriesResponse?> SearchMemoriesAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int maxMemories,
        CancellationToken cancellationToken)
    {
        SearchMemoriesRequest request = new()
        {
            Scope = scope,
            Items = messages.ToArray(),
            Options = new SearchMemoriesOptions { MaxMemories = maxMemories }
        };

        string json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.SearchMemoriesRequest);
        BinaryContent content = BinaryContent.Create(BinaryData.FromString(json));

        RequestOptions requestOptions = new() { CancellationToken = cancellationToken };
        ClientResult result = await client.MemoryStores.SearchMemoriesAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);

        return JsonSerializer.Deserialize(
            result.GetRawResponse().Content.ToString(),
            FoundryMemoryJsonContext.Default.SearchMemoriesResponse);
    }

    /// <summary>
    /// Updates memory store with conversation memories.
    /// </summary>
    internal static async Task<UpdateMemoriesResponse?> UpdateMemoriesAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int updateDelay,
        CancellationToken cancellationToken)
    {
        UpdateMemoriesRequest request = new()
        {
            Scope = scope,
            Items = messages.ToArray(),
            UpdateDelay = updateDelay
        };

        string json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.UpdateMemoriesRequest);
        BinaryContent content = BinaryContent.Create(BinaryData.FromString(json));

        RequestOptions requestOptions = new() { CancellationToken = cancellationToken };
        ClientResult result = await client.MemoryStores.UpdateMemoriesAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);

        return JsonSerializer.Deserialize(
            result.GetRawResponse().Content.ToString(),
            FoundryMemoryJsonContext.Default.UpdateMemoriesResponse);
    }

    /// <summary>
    /// Gets the status of a memory update operation.
    /// </summary>
    internal static async Task<UpdateMemoriesResponse?> GetUpdateStatusAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string updateId,
        CancellationToken cancellationToken)
    {
        RequestOptions requestOptions = new() { CancellationToken = cancellationToken };
        ClientResult result = await client.MemoryStores.GetUpdateResultAsync(memoryStoreName, updateId, requestOptions).ConfigureAwait(false);

        return JsonSerializer.Deserialize(
            result.GetRawResponse().Content.ToString(),
            FoundryMemoryJsonContext.Default.UpdateMemoriesResponse);
    }

    /// <summary>
    /// Deletes all memories associated with a specific scope from a memory store.
    /// </summary>
    internal static async Task DeleteScopeAsync(
        this AIProjectClient client,
        string memoryStoreName,
        string scope,
        CancellationToken cancellationToken)
    {
        DeleteScopeRequest request = new() { Scope = scope };

        string json = JsonSerializer.Serialize(request, FoundryMemoryJsonContext.Default.DeleteScopeRequest);
        BinaryContent content = BinaryContent.Create(BinaryData.FromString(json));

        RequestOptions requestOptions = new() { CancellationToken = cancellationToken };
        await client.MemoryStores.DeleteScopeAsync(memoryStoreName, content, requestOptions).ConfigureAwait(false);
    }
}
