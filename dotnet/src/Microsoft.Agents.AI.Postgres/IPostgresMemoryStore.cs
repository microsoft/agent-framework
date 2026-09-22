// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Internal persistence contract used to test <see cref="PostgresMemoryClient"/> without a live database.
/// </summary>
internal interface IPostgresMemoryStore
{
    Task EnsureSchemaAsync(CancellationToken cancellationToken);

    Task<long> InsertTurnAsync(
        PostgresMemoryScope scope,
        string role,
        string content,
        ReadOnlyMemory<float>? embedding,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRecord>> GetThreadAsync(
        PostgresMemoryScope scope,
        int? recentK,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRecord>> GetTurnsAfterAsync(
        PostgresMemoryScope scope,
        long afterTurnId,
        CancellationToken cancellationToken);

    Task<(int Count, long LatestTurnId)> GetTurnStatsAfterAsync(
        PostgresMemoryScope scope,
        long afterTurnId,
        bool includeThread,
        CancellationToken cancellationToken);

    Task<PostgresMemoryRecord?> FindDuplicateAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType memoryType,
        string contentHash,
        ReadOnlyMemory<float> embedding,
        double similarityThreshold,
        CancellationToken cancellationToken);

    Task<long> InsertDerivedMemoryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType memoryType,
        string content,
        double confidence,
        double? salience,
        IReadOnlyList<string> tags,
        ReadOnlyMemory<float> embedding,
        DateTimeOffset? expiresAt,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRecord>> GetActiveMemoriesAsync(
        PostgresMemoryScope scope,
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int limit,
        double minConfidence,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRecord>> SearchAsync(
        PostgresMemoryScope scope,
        string searchTerms,
        ReadOnlyMemory<float> queryEmbedding,
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int topK,
        double minConfidence,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRerankResult>> RerankAsync(
        string searchTerms,
        IReadOnlyList<PostgresMemoryRecord> candidates,
        string model,
        CancellationToken cancellationToken);

    Task MarkSupersededAsync(
        long supersededId,
        long winnerId,
        string reason,
        CancellationToken cancellationToken);

    Task<(PostgresMemoryRecord? Record, long CoversThroughTurnId)> GetLatestSummaryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType summaryType,
        CancellationToken cancellationToken);

    Task<long?> InsertSummaryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType summaryType,
        string content,
        ReadOnlyMemory<float> embedding,
        long coversThroughTurnId,
        CancellationToken cancellationToken);

    Task<IReadOnlyList<PostgresMemoryRecord>> GetRecentThreadSummariesAsync(
        PostgresMemoryScope scope,
        int limit,
        CancellationToken cancellationToken);

    Task<ProcessingState> GetProcessingStateAsync(string scopeKey, CancellationToken cancellationToken);

    Task UpsertProcessingStateAsync(
        string scopeKey,
        ProcessingState state,
        CancellationToken cancellationToken);
}

internal sealed record PostgresMemoryRerankResult(long Id, int Rank, double RelevanceScore);
