// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Source-generated logging for <see cref="FoundryJsonCheckpointStore"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class FoundryJsonCheckpointStoreLogMessages
{
    [LoggerMessage(LogLevel.Debug, "Attempt {Attempt} of {MaxAttempts} to index checkpoint '{CheckpointId}' for session '{SessionId}' lost to another writer. Retrying.")]
    public static partial void LogCheckpointIndexRaceRetry(
        this ILogger logger,
        int attempt,
        int maxAttempts,
        string checkpointId,
        string sessionId,
        Exception exception);

    [LoggerMessage(LogLevel.Debug, "Obsolete checkpoint '{CheckpointId}' of session '{SessionId}' was already gone.")]
    public static partial void LogObsoleteCheckpointAlreadyGone(
        this ILogger logger,
        string checkpointId,
        string sessionId,
        Exception exception);

    [LoggerMessage(LogLevel.Debug, "Pruning obsolete checkpoints of session '{SessionId}' lost to another writer. The old checkpoints remain until a later resume or expiry.")]
    public static partial void LogCheckpointPruningRace(
        this ILogger logger,
        string sessionId,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Could not prune obsolete checkpoints of session '{SessionId}' in the Foundry state store '{StoreName}'. The resume itself succeeded; the leftovers stay until the store's own expiry removes them.")]
    public static partial void LogCheckpointPruningFailed(
        this ILogger logger,
        string sessionId,
        string storeName,
        Exception exception);
}
