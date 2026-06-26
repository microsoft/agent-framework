// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Host-execution metadata store, limited to v1 scope: reset-session aliases and workflow checkpoint path
/// derivation. It does NOT store linked identities, active-channel state, response routing, continuation
/// records, durable runner queues, or delivery attempts (those are ADR-0028 concerns). Separate from
/// <c>AgentSessionStore</c> (per-conversation history) and <c>WorkflowBuilder.CheckpointStorage</c>
/// (workflow checkpoints).
/// </summary>
public interface IHostStateStore
{
    /// <summary>
    /// Rotate the active session-id alias for an isolation key. Backs
    /// <see cref="AgentFrameworkHost.ResetSessionAsync"/> for host-tracked channels' <c>/new</c>-style commands.
    /// </summary>
    ValueTask RotateSessionAliasAsync(string isolationKey, CancellationToken cancellationToken);

    /// <summary>Read the active session-id alias for an isolation key.</summary>
    ValueTask<string?> GetActiveSessionAliasAsync(string isolationKey, CancellationToken cancellationToken);

    /// <summary>
    /// Derive the persistent workflow checkpoint location for an isolation key, or <see langword="null"/>
    /// when this store does not persist checkpoints (e.g. the in-memory store). Implementations must reject
    /// path-traversal patterns in the isolation key.
    /// </summary>
    ValueTask<string?> GetCheckpointLocationAsync(string isolationKey, CancellationToken cancellationToken);
}
