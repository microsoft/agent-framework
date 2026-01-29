// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Interface for Foundry Memory operations, enabling testability.
/// </summary>
internal interface IFoundryMemoryOperations
{
    /// <summary>
    /// Searches for relevant memories from a memory store based on conversation context.
    /// </summary>
    Task<IEnumerable<string>> SearchMemoriesAsync(
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int maxMemories,
        CancellationToken cancellationToken);

    /// <summary>
    /// Updates memory store with conversation memories.
    /// </summary>
    Task UpdateMemoriesAsync(
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int updateDelay,
        CancellationToken cancellationToken);

    /// <summary>
    /// Deletes all memories associated with a specific scope from a memory store.
    /// </summary>
    Task DeleteScopeAsync(
        string memoryStoreName,
        string scope,
        CancellationToken cancellationToken);
}
