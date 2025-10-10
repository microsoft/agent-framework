// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides an in-memory implementation of <see cref="IAgentThreadStore"/> for development and testing scenarios.
/// </summary>
/// <remarks>
/// <para>
/// This implementation stores threads in memory using a concurrent dictionary and is suitable for:
/// <list type="bullet">
/// <item><description>Single-instance development scenarios</description></item>
/// <item><description>Testing and prototyping</description></item>
/// <item><description>Scenarios where thread persistence across restarts is not required</description></item>
/// </list>
/// </para>
/// <para>
/// <strong>Warning:</strong> All stored threads will be lost when the application restarts.
/// For production use with multiple instances or persistence across restarts, use a durable storage implementation
/// such as Redis, SQL Server, or Azure Cosmos DB.
/// </para>
/// </remarks>
public sealed class InMemoryAgentThreadStore : IAgentThreadStore
{
    private readonly ConcurrentDictionary<string, JsonElement> _threads = new();

    /// <inheritdoc/>
    public ValueTask SaveThreadAsync(
        string conversationId,
        string agentId,
        JsonElement serializedThread,
        CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agentId);
        this._threads[key] = serializedThread;
        return default;
    }

    /// <inheritdoc/>
    public ValueTask<JsonElement?> GetOrCreateThreadAsync(
        string conversationId,
        string agentId,
        CancellationToken cancellationToken = default)
    {
        var key = GetKey(conversationId, agentId);
        var threadContent = this._threads.GetOrAdd(key, value: JsonDocument.Parse("{}").RootElement);
        return new ValueTask<JsonElement?>(threadContent);
    }

    private static string GetKey(string conversationId, string agentId)
        => $"{agentId}:{conversationId}";
}
