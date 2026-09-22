// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Internal provider-facing contract implemented by <see cref="PostgresMemoryClient"/>.
/// </summary>
internal interface IPostgresMemoryClient
{
    /// <summary>
    /// Stores one raw conversation turn.
    /// </summary>
    Task<long> UpsertMemoryAsync(
        PostgresMemoryScope scope,
        string role,
        string content,
        CancellationToken cancellationToken);

    /// <summary>
    /// Searches active derived memories.
    /// </summary>
    Task<IReadOnlyList<PostgresMemoryRecord>> SearchAsync(
        PostgresMemoryScope scope,
        string searchTerms,
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int topK,
        double minConfidence,
        CancellationToken cancellationToken);

    /// <summary>
    /// Retrieves the current cross-thread user summary.
    /// </summary>
    Task<PostgresMemoryRecord?> GetUserSummaryAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken);

    /// <summary>
    /// Runs all memory-processing steps immediately.
    /// </summary>
    Task ProcessNowAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken);

    /// <summary>
    /// Waits for background processing already scheduled by turn writes.
    /// </summary>
    Task FlushAsync(CancellationToken cancellationToken);
}
