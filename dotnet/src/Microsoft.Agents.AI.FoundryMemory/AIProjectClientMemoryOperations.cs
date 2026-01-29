// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Implementation of <see cref="IFoundryMemoryOperations"/> using <see cref="AIProjectClient"/>.
/// </summary>
internal sealed class AIProjectClientMemoryOperations : IFoundryMemoryOperations
{
    private readonly AIProjectClient _client;

    public AIProjectClientMemoryOperations(AIProjectClient client)
    {
        this._client = client;
    }

    public Task<IEnumerable<string>> SearchMemoriesAsync(
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int maxMemories,
        CancellationToken cancellationToken)
    {
        return this._client.SearchMemoriesAsync(memoryStoreName, scope, messages, maxMemories, cancellationToken);
    }

    public Task UpdateMemoriesAsync(
        string memoryStoreName,
        string scope,
        IEnumerable<MemoryInputMessage> messages,
        int updateDelay,
        CancellationToken cancellationToken)
    {
        return this._client.UpdateMemoriesAsync(memoryStoreName, scope, messages, updateDelay, cancellationToken);
    }

    public Task DeleteScopeAsync(
        string memoryStoreName,
        string scope,
        CancellationToken cancellationToken)
    {
        return this._client.DeleteScopeAsync(memoryStoreName, scope, cancellationToken);
    }
}
