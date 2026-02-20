// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Internal extension methods for <see cref="AIProjectClient"/> to provide MemoryStores helper operations.
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
        try
        {
            await client.MemoryStores.GetMemoryStoreAsync(memoryStoreName, cancellationToken).ConfigureAwait(false);
            return false; // Store already exists
        }
        catch (ClientResultException ex) when (ex.Status == 404)
        {
            // Store doesn't exist, create it
        }

        MemoryStoreDefaultDefinition definition = new(chatModel, embeddingModel);
        await client.MemoryStores.CreateMemoryStoreAsync(memoryStoreName, definition, description, cancellationToken: cancellationToken).ConfigureAwait(false);
        return true;
    }
}
