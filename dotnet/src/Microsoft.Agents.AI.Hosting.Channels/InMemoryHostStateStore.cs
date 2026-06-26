// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// In-memory <see cref="IHostStateStore"/>. Volatile; intended for tests, samples, and single-process
/// development. Thread-safe.
/// </summary>
public sealed class InMemoryHostStateStore : IHostStateStore
{
    private readonly ConcurrentDictionary<string, string> _sessionAliases = new(StringComparer.Ordinal);

    /// <inheritdoc />
    public ValueTask RotateSessionAliasAsync(string isolationKey, CancellationToken cancellationToken)
    {
        Throw.IfNullOrEmpty(isolationKey);
        this._sessionAliases[isolationKey] = Guid.NewGuid().ToString("N");
        return default;
    }

    /// <inheritdoc />
    public ValueTask<string?> GetActiveSessionAliasAsync(string isolationKey, CancellationToken cancellationToken)
    {
        Throw.IfNullOrEmpty(isolationKey);
        if (!this._sessionAliases.TryGetValue(isolationKey, out var alias))
        {
            alias = isolationKey;
            this._sessionAliases.TryAdd(isolationKey, alias);
        }
        return new(alias);
    }

    /// <inheritdoc />
    public ValueTask<string?> GetCheckpointLocationAsync(string isolationKey, CancellationToken cancellationToken)
    {
        Throw.IfNullOrEmpty(isolationKey);

        // The in-memory store does not persist checkpoints, so there is no on-disk location to derive.
        return default;
    }
}
