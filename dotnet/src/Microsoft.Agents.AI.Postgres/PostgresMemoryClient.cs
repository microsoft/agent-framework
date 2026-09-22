// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Stores, retrieves, and transforms durable agent memory using PostgreSQL and pgvector.
/// </summary>
/// <remarks>
/// <para>
/// This client owns the durable memory model and processing pipeline;
/// <see cref="PostgresMemoryContextProvider"/> is the Agent Framework lifecycle adapter.
/// </para>
/// <para>
/// The client stores raw turns separately from derived <see cref="PostgresMemoryType.Fact"/>,
/// <see cref="PostgresMemoryType.Procedural"/>, and <see cref="PostgresMemoryType.Episodic"/>
/// memories. It also maintains incremental thread and user summaries, supports hybrid vector/full-text
/// retrieval, and reconciles contradictory memories by preserving supersession history.
/// </para>
/// </remarks>
public sealed class PostgresMemoryClient : IPostgresMemoryClient, IAsyncDisposable
{
    private static readonly PostgresMemoryType[] s_derivedMemoryTypes =
        [PostgresMemoryType.Fact, PostgresMemoryType.Procedural, PostgresMemoryType.Episodic];

    private readonly IPostgresMemoryStore _store;
#pragma warning disable CA2213 // Model clients are supplied and owned by the caller.
    private readonly IEmbeddingGenerator<string, Embedding<float>> _embeddingGenerator;
    private readonly IChatClient _chatClient;
#pragma warning restore CA2213
    private readonly PostgresMemoryClientOptions _options;
    private readonly ILogger<PostgresMemoryClient>? _logger;
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _processingLocks = new();
    private readonly ConcurrentDictionary<long, Task> _backgroundTasks = new();
    private long _nextBackgroundTaskId;
    private bool _disposed;

    /// <summary>
    /// Initializes a new instance of the <see cref="PostgresMemoryClient"/> class.
    /// </summary>
    /// <param name="dataSource">
    /// A configured data source built with pgvector support, for example
    /// <c>new NpgsqlDataSourceBuilder(connectionString).UseVector().Build()</c>.
    /// </param>
    /// <param name="embeddingGenerator">The embedding generator used for storage and retrieval.</param>
    /// <param name="chatClient">The chat client used for extraction, summaries, and reconciliation.</param>
    /// <param name="options">Client options.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public PostgresMemoryClient(
        NpgsqlDataSource dataSource,
        IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator,
        IChatClient chatClient,
        PostgresMemoryClientOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this(
            new PostgresMemoryStore(Throw.IfNull(dataSource), options ?? new PostgresMemoryClientOptions()),
            embeddingGenerator,
            chatClient,
            options,
            loggerFactory)
    {
    }

    /// <summary>
    /// Initializes an instance over an injected persistence store for testing.
    /// </summary>
    internal PostgresMemoryClient(
        IPostgresMemoryStore store,
        IEmbeddingGenerator<string, Embedding<float>> embeddingGenerator,
        IChatClient chatClient,
        PostgresMemoryClientOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        this._store = Throw.IfNull(store);
        this._embeddingGenerator = Throw.IfNull(embeddingGenerator);
        this._chatClient = Throw.IfNull(chatClient);
        this._options = options ?? new PostgresMemoryClientOptions();
        ValidateOptions(this._options);
        this._logger = loggerFactory?.CreateLogger<PostgresMemoryClient>();
    }

    /// <summary>
    /// Stores one raw conversation turn and schedules cadence-aware processing when enabled.
    /// </summary>
    /// <param name="scope">The durable user and thread scope.</param>
    /// <param name="role">The turn role: user, agent/assistant, tool, or system.</param>
    /// <param name="content">The turn content.</param>
    /// <param name="cancellationToken">A cancellation token.</param>
    /// <returns>The database-generated turn identifier.</returns>
    public async Task<long> UpsertMemoryAsync(
        PostgresMemoryScope scope,
        string role,
        string content,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateThreadScope(scope);
        role = NormalizeRole(Throw.IfNullOrWhitespace(role));
        content = Throw.IfNullOrWhitespace(content).Trim();

        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);

        ReadOnlyMemory<float>? embedding = null;
        if (this._options.EnableTurnEmbeddings)
        {
            embedding = await this._embeddingGenerator.GenerateVectorAsync(content, cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        var id = await this._store.InsertTurnAsync(scope, role, content, embedding, cancellationToken).ConfigureAwait(false);

        if (this._options.AutoProcess)
        {
            this.ScheduleBackgroundProcessing(new PostgresMemoryScope(scope));
        }

        return id;
    }

    /// <summary>
    /// Gets raw turns for one conversation in chronological order.
    /// </summary>
    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetThreadAsync(
        PostgresMemoryScope scope,
        int? recentK = null,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateThreadScope(scope);
        if (recentK is <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(recentK));
        }

        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        return await this._store.GetThreadAsync(scope, recentK, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Gets active derived memories for a user, optionally constrained to a thread.
    /// </summary>
    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetMemoriesAsync(
        PostgresMemoryScope scope,
        IReadOnlyList<PostgresMemoryType>? memoryTypes = null,
        int limit = 50,
        double minConfidence = 0,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateUserScope(scope);
        ValidateRetrievalArguments(memoryTypes ?? s_derivedMemoryTypes, limit, minConfidence);

        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        return await this._store.GetActiveMemoriesAsync(
            scope,
            memoryTypes ?? s_derivedMemoryTypes,
            limit,
            minConfidence,
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Searches active derived memories with hybrid vector and full-text retrieval.
    /// </summary>
    public async Task<IReadOnlyList<PostgresMemoryRecord>> SearchAsync(
        PostgresMemoryScope scope,
        string searchTerms,
        IReadOnlyList<PostgresMemoryType>? memoryTypes = null,
        int topK = 5,
        double minConfidence = 0.7,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateUserScope(scope);
        searchTerms = Throw.IfNullOrWhitespace(searchTerms);
        var selectedTypes = memoryTypes ?? s_derivedMemoryTypes;
        ValidateRetrievalArguments(selectedTypes, topK, minConfidence);

        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        var embedding = await this._embeddingGenerator.GenerateVectorAsync(searchTerms, cancellationToken: cancellationToken).ConfigureAwait(false);
        var candidateCount = this._options.EnableAzureAiReranking
            ? Math.Max(topK, this._options.RerankingCandidateCount)
            : topK;
        var candidates = await this._store.SearchAsync(
            scope,
            searchTerms,
            embedding,
            selectedTypes,
            candidateCount,
            minConfidence,
            cancellationToken).ConfigureAwait(false);

        if (!this._options.EnableAzureAiReranking || candidates.Count <= 1)
        {
            return candidates;
        }

        try
        {
            var reranked = await this._store.RerankAsync(
                searchTerms,
                candidates,
                this._options.AzureAiRerankerModel,
                cancellationToken).ConfigureAwait(false);
            var candidatesById = candidates.ToDictionary(candidate => candidate.Id);
            var results = new List<PostgresMemoryRecord>(topK);
            var selectedIds = new HashSet<long>();

            foreach (var result in reranked.OrderBy(result => result.Rank))
            {
                if (candidatesById.TryGetValue(result.Id, out var candidate) && selectedIds.Add(result.Id))
                {
                    results.Add(candidate.WithRerankerScore(result.RelevanceScore));
                    if (results.Count == topK)
                    {
                        return results;
                    }
                }
            }

            foreach (var candidate in candidates)
            {
                if (selectedIds.Add(candidate.Id))
                {
                    results.Add(candidate);
                    if (results.Count == topK)
                    {
                        break;
                    }
                }
            }

            return results;
        }
        catch (NpgsqlException ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Warning) is true)
            {
                this._logger.LogWarning(ex, "Azure AI memory reranking failed; returning hybrid retrieval order.");
            }

            return candidates.Take(topK).ToArray();
        }
    }

    /// <summary>
    /// Gets the latest cross-thread user summary.
    /// </summary>
    public async Task<PostgresMemoryRecord?> GetUserSummaryAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateUserScope(scope);
        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        var (record, _) = await this._store.GetLatestSummaryAsync(
            scope.ToUserScope(),
            PostgresMemoryType.UserSummary,
            cancellationToken).ConfigureAwait(false);
        return record;
    }

    /// <summary>
    /// Extracts typed memories from turns not previously processed for the thread.
    /// </summary>
    /// <returns>The number of newly inserted memories.</returns>
    public async Task<int> ExtractMemoriesAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateThreadScope(scope);
        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);

        var processingLock = this.GetProcessingLock(scope, includeThread: true);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await this.ExtractMemoriesCoreAsync(scope, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            processingLock.Release();
        }
    }

    private async Task<int> ExtractMemoriesCoreAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken)
    {
        var scopeKey = PostgresMemoryStore.ComputeScopeKey(scope, includeThread: true);
        var state = await this._store.GetProcessingStateAsync(scopeKey, cancellationToken).ConfigureAwait(false);
        var turns = await this._store.GetTurnsAfterAsync(scope, state.FactThroughTurnId, cancellationToken).ConfigureAwait(false);
        if (turns.Count == 0)
        {
            return 0;
        }

        var existingMemories = await this._store.GetActiveMemoriesAsync(
            scope.ToUserScope(),
            s_derivedMemoryTypes,
            50,
            0,
            cancellationToken).ConfigureAwait(false);

        var response = await this._chatClient.GetResponseAsync(
            PostgresMemoryPrompts.BuildExtractMemoriesMessages(this._options.Prompts.ExtractMemories, turns, existingMemories),
            options: null,
            cancellationToken).ConfigureAwait(false);

        if (!TryParseExtractedMemories(response.Text, out var candidates))
        {
            throw new InvalidOperationException(
                "The memory extraction model response was not a valid JSON array of typed memories.");
        }

        var inserted = 0;
        foreach (var candidate in candidates)
        {
            var embedding = await this._embeddingGenerator.GenerateVectorAsync(
                candidate.Content,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            var duplicate = await this._store.FindDuplicateAsync(
                scope.ToUserScope(),
                candidate.MemoryType,
                ComputeContentHash(candidate.Content),
                embedding,
                this._options.DedupeSimilarityThreshold,
                cancellationToken).ConfigureAwait(false);
            if (duplicate is not null)
            {
                continue;
            }

            DateTimeOffset? expiresAt = candidate.MemoryType == PostgresMemoryType.Episodic
                && this._options.EpisodicMemoryTimeToLive.HasValue
                ? DateTimeOffset.UtcNow.Add(this._options.EpisodicMemoryTimeToLive.Value)
                : null;

            _ = await this._store.InsertDerivedMemoryAsync(
                scope,
                candidate.MemoryType,
                candidate.Content,
                candidate.Confidence,
                candidate.Salience,
                candidate.Tags,
                embedding,
                expiresAt,
                cancellationToken).ConfigureAwait(false);
            inserted++;
        }

        var latestTurnId = turns[^1].Id;
        state = state with
        {
            FactThroughTurnId = latestTurnId,
            ExtractionRuns = state.ExtractionRuns + 1,
        };
        await this._store.UpsertProcessingStateAsync(scopeKey, state, cancellationToken).ConfigureAwait(false);
        return inserted;
    }

    /// <summary>
    /// Generates or incrementally updates the summary for one conversation thread.
    /// </summary>
    public async Task<PostgresMemoryRecord?> GenerateThreadSummaryAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateThreadScope(scope);
        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);

        var processingLock = this.GetProcessingLock(scope, includeThread: true);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await this.GenerateThreadSummaryCoreAsync(scope, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            processingLock.Release();
        }
    }

    private async Task<PostgresMemoryRecord?> GenerateThreadSummaryCoreAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken)
    {
        var (previous, coversThrough) = await this._store.GetLatestSummaryAsync(
            scope,
            PostgresMemoryType.Summary,
            cancellationToken).ConfigureAwait(false);
        var turns = await this._store.GetTurnsAfterAsync(scope, coversThrough, cancellationToken).ConfigureAwait(false);
        if (turns.Count == 0)
        {
            return previous;
        }

        var response = await this._chatClient.GetResponseAsync(
            PostgresMemoryPrompts.BuildThreadSummaryMessages(this._options.Prompts.ThreadSummary, previous?.Content, turns),
            options: null,
            cancellationToken).ConfigureAwait(false);
        var summary = response.Text?.Trim();
        if (string.IsNullOrWhiteSpace(summary))
        {
            return previous;
        }

        var embedding = await this._embeddingGenerator.GenerateVectorAsync(summary, cancellationToken: cancellationToken).ConfigureAwait(false);
        var latestTurnId = turns[^1].Id;
        var id = await this._store.InsertSummaryAsync(
            scope,
            PostgresMemoryType.Summary,
            summary,
            embedding,
            latestTurnId,
            cancellationToken).ConfigureAwait(false);

        if (!id.HasValue)
        {
            var (latest, _) = await this._store.GetLatestSummaryAsync(
                scope,
                PostgresMemoryType.Summary,
                cancellationToken).ConfigureAwait(false);
            return latest;
        }

        var scopeKey = PostgresMemoryStore.ComputeScopeKey(scope, includeThread: true);
        var state = await this._store.GetProcessingStateAsync(scopeKey, cancellationToken).ConfigureAwait(false);
        await this._store.UpsertProcessingStateAsync(
            scopeKey,
            state with { SummaryThroughTurnId = latestTurnId },
            cancellationToken).ConfigureAwait(false);

        return CreateSummaryRecord(id.Value, scope, PostgresMemoryType.Summary, summary);
    }

    /// <summary>
    /// Generates or incrementally updates the cross-thread user summary.
    /// </summary>
    public async Task<PostgresMemoryRecord?> GenerateUserSummaryAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateUserScope(scope);
        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);

        var userScope = scope.ToUserScope();
        var processingLock = this.GetProcessingLock(userScope, includeThread: false);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await this.GenerateUserSummaryCoreAsync(userScope, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            processingLock.Release();
        }
    }

    private async Task<PostgresMemoryRecord?> GenerateUserSummaryCoreAsync(
        PostgresMemoryScope userScope,
        CancellationToken cancellationToken)
    {
        var (previous, _) = await this._store.GetLatestSummaryAsync(
            userScope,
            PostgresMemoryType.UserSummary,
            cancellationToken).ConfigureAwait(false);
        var (_, latestTurnId) = await this._store.GetTurnStatsAfterAsync(
            userScope,
            0,
            includeThread: false,
            cancellationToken).ConfigureAwait(false);
        var memories = await this._store.GetActiveMemoriesAsync(
            userScope,
            s_derivedMemoryTypes,
            100,
            0.5,
            cancellationToken).ConfigureAwait(false);
        var summaries = await this._store.GetRecentThreadSummariesAsync(userScope, 25, cancellationToken).ConfigureAwait(false);
        if (memories.Count == 0 && summaries.Count == 0)
        {
            return previous;
        }

        var response = await this._chatClient.GetResponseAsync(
            PostgresMemoryPrompts.BuildUserSummaryMessages(
                this._options.Prompts.UserSummary,
                previous?.Content,
                memories,
                summaries),
            options: null,
            cancellationToken).ConfigureAwait(false);
        var summary = response.Text?.Trim();
        if (string.IsNullOrWhiteSpace(summary))
        {
            return previous;
        }

        var embedding = await this._embeddingGenerator.GenerateVectorAsync(summary, cancellationToken: cancellationToken).ConfigureAwait(false);
        var id = await this._store.InsertSummaryAsync(
            userScope,
            PostgresMemoryType.UserSummary,
            summary,
            embedding,
            latestTurnId,
            cancellationToken).ConfigureAwait(false);

        if (!id.HasValue)
        {
            var (latest, _) = await this._store.GetLatestSummaryAsync(
                userScope,
                PostgresMemoryType.UserSummary,
                cancellationToken).ConfigureAwait(false);
            return latest;
        }

        var scopeKey = PostgresMemoryStore.ComputeScopeKey(userScope, includeThread: false);
        var state = await this._store.GetProcessingStateAsync(scopeKey, cancellationToken).ConfigureAwait(false);
        await this._store.UpsertProcessingStateAsync(
            scopeKey,
            state with { UserSummaryThroughTurnId = latestTurnId },
            cancellationToken).ConfigureAwait(false);

        return CreateSummaryRecord(id.Value, userScope, PostgresMemoryType.UserSummary, summary);
    }

    /// <summary>
    /// Reconciles semantic contradictions among recent active memories, preserving an audit trail.
    /// </summary>
    /// <returns>The number of memories marked as superseded.</returns>
    public async Task<int> ReconcileAsync(
        PostgresMemoryScope scope,
        int? poolSize = null,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateUserScope(scope);
        var limit = poolSize ?? this._options.ReconciliationPoolSize;
        if (limit is < 2 or > 500)
        {
            throw new ArgumentOutOfRangeException(nameof(poolSize), "Reconciliation pool size must be between 2 and 500.");
        }

        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        var userScope = scope.ToUserScope();
        var processingLock = this.GetProcessingLock(userScope, includeThread: false);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return await this.ReconcileCoreAsync(userScope, limit, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            processingLock.Release();
        }
    }

    private async Task<int> ReconcileCoreAsync(
        PostgresMemoryScope userScope,
        int limit,
        CancellationToken cancellationToken)
    {
        var memories = await this._store.GetActiveMemoriesAsync(
            userScope,
            s_derivedMemoryTypes,
            limit,
            0,
            cancellationToken).ConfigureAwait(false);
        if (memories.Count < 2)
        {
            return 0;
        }

        var response = await this._chatClient.GetResponseAsync(
            PostgresMemoryPrompts.BuildReconcileMessages(this._options.Prompts.Reconcile, memories),
            options: null,
            cancellationToken).ConfigureAwait(false);

        var validIds = memories.Select(m => m.Id).ToHashSet();
        if (!TryParseReconciliationDecisions(response.Text, out var decisions))
        {
            throw new InvalidOperationException(
                "The memory reconciliation model response was not a valid JSON array of decisions.");
        }

        var reconciled = 0;
        foreach (var decision in decisions)
        {
            if (decision.SupersededId == decision.WinnerId
                || !validIds.Contains(decision.SupersededId)
                || !validIds.Contains(decision.WinnerId))
            {
                continue;
            }

            await this._store.MarkSupersededAsync(
                decision.SupersededId,
                decision.WinnerId,
                decision.Reason,
                cancellationToken).ConfigureAwait(false);
            reconciled++;
        }

        return reconciled;
    }

    /// <summary>
    /// Runs extraction, thread summarization, user summarization, and reconciliation immediately.
    /// </summary>
    public async Task ProcessNowAsync(
        PostgresMemoryScope scope,
        CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();
        ValidateThreadScope(scope);
        await this.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);

        var processingLock = this.GetProcessingLock(scope, includeThread: true);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            _ = await this.ExtractMemoriesCoreAsync(scope, cancellationToken).ConfigureAwait(false);
            _ = await this.GenerateThreadSummaryCoreAsync(scope, cancellationToken).ConfigureAwait(false);
            _ = await this.GenerateUserSummaryAsync(scope, cancellationToken).ConfigureAwait(false);
            _ = await this.ReconcileAsync(scope.ToUserScope(), cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            processingLock.Release();
        }
    }

    /// <summary>
    /// Waits until currently scheduled background processing has completed.
    /// </summary>
    public async Task FlushAsync(CancellationToken cancellationToken = default)
    {
        this.ThrowIfDisposed();

        while (!this._backgroundTasks.IsEmpty)
        {
            var tasks = this._backgroundTasks.Values.ToArray();
            if (tasks.Length == 0)
            {
                return;
            }

            await Task.WhenAll(tasks).WaitAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (this._disposed)
        {
            return;
        }

        await this.FlushAsync(CancellationToken.None).ConfigureAwait(false);
        this._disposed = true;
        foreach (var processingLock in this._processingLocks.Values)
        {
            processingLock.Dispose();
        }

        this._processingLocks.Clear();
    }

    private async Task EnsureSchemaAsync(CancellationToken cancellationToken)
    {
        if (this._options.EnsureSchemaOnFirstUse)
        {
            await this._store.EnsureSchemaAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    private void ScheduleBackgroundProcessing(PostgresMemoryScope scope)
    {
        var taskId = Interlocked.Increment(ref this._nextBackgroundTaskId);
        this._backgroundTasks[taskId] = this.RunBackgroundProcessingAsync(taskId, scope);
    }

    private async Task RunBackgroundProcessingAsync(long taskId, PostgresMemoryScope scope)
    {
        await Task.Yield();
        try
        {
            await this.ProcessDueStepsAsync(scope, CancellationToken.None).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            if (this._logger?.IsEnabled(LogLevel.Warning) is true)
            {
                this._logger.LogWarning(
                    ex,
                    "Background PostgreSQL memory processing failed for user '{UserId}', thread '{ThreadId}'.",
                    scope.UserId,
                    scope.ThreadId);
            }
        }
        finally
        {
            _ = this._backgroundTasks.TryRemove(taskId, out _);
        }
    }

    private async Task ProcessDueStepsAsync(PostgresMemoryScope scope, CancellationToken cancellationToken)
    {
        var processingLock = this.GetProcessingLock(scope, includeThread: true);
        await processingLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var threadKey = PostgresMemoryStore.ComputeScopeKey(scope, includeThread: true);
            var threadState = await this._store.GetProcessingStateAsync(threadKey, cancellationToken).ConfigureAwait(false);

            if (this._options.FactExtractionEveryNTurns > 0)
            {
                var (count, _) = await this._store.GetTurnStatsAfterAsync(
                    scope,
                    threadState.FactThroughTurnId,
                    includeThread: true,
                    cancellationToken).ConfigureAwait(false);
                if (count >= this._options.FactExtractionEveryNTurns)
                {
                    _ = await this.ExtractMemoriesCoreAsync(scope, cancellationToken).ConfigureAwait(false);
                    threadState = await this._store.GetProcessingStateAsync(threadKey, cancellationToken).ConfigureAwait(false);
                    if (this._options.ReconcileEveryNExtractions > 0
                        && threadState.ExtractionRuns % this._options.ReconcileEveryNExtractions == 0)
                    {
                        _ = await this.ReconcileAsync(scope.ToUserScope(), cancellationToken: cancellationToken).ConfigureAwait(false);
                    }
                }
            }

            if (this._options.ThreadSummaryEveryNTurns > 0)
            {
                var (count, _) = await this._store.GetTurnStatsAfterAsync(
                    scope,
                    threadState.SummaryThroughTurnId,
                    includeThread: true,
                    cancellationToken).ConfigureAwait(false);
                if (count >= this._options.ThreadSummaryEveryNTurns)
                {
                    _ = await this.GenerateThreadSummaryCoreAsync(scope, cancellationToken).ConfigureAwait(false);
                }
            }

            if (this._options.UserSummaryEveryNTurns > 0)
            {
                var userScope = scope.ToUserScope();
                var userKey = PostgresMemoryStore.ComputeScopeKey(userScope, includeThread: false);
                var userState = await this._store.GetProcessingStateAsync(userKey, cancellationToken).ConfigureAwait(false);
                var (count, _) = await this._store.GetTurnStatsAfterAsync(
                    userScope,
                    userState.UserSummaryThroughTurnId,
                    includeThread: false,
                    cancellationToken).ConfigureAwait(false);
                if (count >= this._options.UserSummaryEveryNTurns)
                {
                    _ = await this.GenerateUserSummaryAsync(userScope, cancellationToken).ConfigureAwait(false);
                }
            }
        }
        finally
        {
            processingLock.Release();
        }
    }

    private SemaphoreSlim GetProcessingLock(PostgresMemoryScope scope, bool includeThread)
    {
        var key = PostgresMemoryStore.ComputeScopeKey(scope, includeThread);
        return this._processingLocks.GetOrAdd(key, static _ => new SemaphoreSlim(1, 1));
    }

    private static PostgresMemoryRecord CreateSummaryRecord(
        long id,
        PostgresMemoryScope scope,
        PostgresMemoryType memoryType,
        string content)
    {
        var now = DateTimeOffset.UtcNow;
        return new PostgresMemoryRecord
        {
            Id = id,
            MemoryType = memoryType,
            Content = content,
            UserId = scope.UserId!,
            ThreadId = scope.ThreadId,
            AgentId = scope.AgentId,
            ApplicationId = scope.ApplicationId,
            CreatedAt = now,
            UpdatedAt = now,
        };
    }

    private static bool TryParseExtractedMemories(
        string? responseText,
        out List<ExtractedMemory> results)
    {
        results = [];
        if (string.IsNullOrWhiteSpace(responseText))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(responseText.Trim());
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            foreach (var item in document.RootElement.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object
                    || !item.TryGetProperty("content", out var contentElement)
                    || contentElement.ValueKind != JsonValueKind.String
                    || !item.TryGetProperty("memory_type", out var typeElement)
                    || typeElement.ValueKind != JsonValueKind.String
                    || !item.TryGetProperty("confidence", out var confidenceElement)
                    || !TryParseScore(confidenceElement, out var confidence))
                {
                    return false;
                }

                var content = contentElement.GetString()?.Trim();
                var typeText = typeElement.GetString();
                if (string.IsNullOrWhiteSpace(content) || !TryParseDerivedMemoryType(typeText, out var memoryType))
                {
                    return false;
                }

                double? salience = null;
                if (item.TryGetProperty("salience", out var salienceElement)
                    && salienceElement.ValueKind != JsonValueKind.Null)
                {
                    if (!TryParseScore(salienceElement, out var parsedSalience))
                    {
                        return false;
                    }

                    salience = parsedSalience;
                }

                var tags = new List<string>();
                if (item.TryGetProperty("tags", out var tagsElement)
                    && tagsElement.ValueKind != JsonValueKind.Null)
                {
                    if (tagsElement.ValueKind != JsonValueKind.Array)
                    {
                        return false;
                    }

                    foreach (var tagElement in tagsElement.EnumerateArray())
                    {
                        var tag = tagElement.ValueKind == JsonValueKind.String
                            ? tagElement.GetString()?.Trim()
                            : null;
                        if (string.IsNullOrWhiteSpace(tag))
                        {
                            return false;
                        }

                        tags.Add(tag);
                    }
                }

                results.Add(new ExtractedMemory(content, memoryType, confidence, salience, tags));
            }

            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool TryParseReconciliationDecisions(
        string? responseText,
        out List<ReconciliationDecision> results)
    {
        results = [];
        if (string.IsNullOrWhiteSpace(responseText))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(responseText.Trim());
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                return false;
            }

            foreach (var item in document.RootElement.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object
                    || !item.TryGetProperty("superseded_id", out var supersededElement)
                    || !item.TryGetProperty("winner_id", out var winnerElement)
                    || supersededElement.ValueKind != JsonValueKind.Number
                    || winnerElement.ValueKind != JsonValueKind.Number
                    || !supersededElement.TryGetInt64(out var supersededId)
                    || !winnerElement.TryGetInt64(out var winnerId)
                    || !item.TryGetProperty("reason", out var reasonElement)
                    || reasonElement.ValueKind != JsonValueKind.String)
                {
                    return false;
                }

                var reason = reasonElement.GetString()?.Trim();
                if (string.IsNullOrWhiteSpace(reason))
                {
                    return false;
                }

                results.Add(new ReconciliationDecision(supersededId, winnerId, reason));
            }

            return true;
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool TryParseScore(JsonElement element, out double score)
    {
        score = 0;
        return element.ValueKind == JsonValueKind.Number
            && element.TryGetDouble(out score)
            && double.IsFinite(score)
            && score is >= 0 and <= 1;
    }

    private static bool TryParseDerivedMemoryType(string? value, out PostgresMemoryType memoryType)
    {
        memoryType = value?.Trim().ToUpperInvariant() switch
        {
            "FACT" => PostgresMemoryType.Fact,
            "PROCEDURAL" => PostgresMemoryType.Procedural,
            "EPISODIC" => PostgresMemoryType.Episodic,
            _ => PostgresMemoryType.Turn,
        };
        return memoryType != PostgresMemoryType.Turn;
    }

    private static string ComputeContentHash(string content)
    {
        var normalized = content.Trim().ToUpperInvariant();
        return Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes(normalized)));
    }

    private static string NormalizeRole(string role) =>
        role.Trim().ToUpperInvariant() switch
        {
            "ASSISTANT" => "agent",
            "AGENT" => "agent",
            "USER" => "user",
            "TOOL" => "tool",
            "SYSTEM" => "system",
            _ => throw new ArgumentException($"Unsupported memory role '{role}'.", nameof(role)),
        };

    private static void ValidateOptions(PostgresMemoryClientOptions options)
    {
        if (options.EmbeddingDimensions is < 1 or > 2000)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                "EmbeddingDimensions must be between 1 and 2000 for the vector index.");
        }

        if (options.RerankingCandidateCount <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "RerankingCandidateCount must be greater than zero.");
        }

        if (options.EnableAzureAiReranking && string.IsNullOrWhiteSpace(options.AzureAiRerankerModel))
        {
            throw new ArgumentException("AzureAiRerankerModel is required when Azure AI reranking is enabled.", nameof(options));
        }

        if (options.FactExtractionEveryNTurns < 0
            || options.ReconcileEveryNExtractions < 0
            || options.ThreadSummaryEveryNTurns < 0
            || options.UserSummaryEveryNTurns < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "Processing cadence values cannot be negative.");
        }

        if (options.ReconciliationPoolSize is < 2 or > 500)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "ReconciliationPoolSize must be between 2 and 500.");
        }

        if (options.DedupeSimilarityThreshold is < 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(nameof(options), "DedupeSimilarityThreshold must be between 0 and 1.");
        }
    }

    private static void ValidateRetrievalArguments(
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int limit,
        double minConfidence)
    {
        if (memoryTypes.Count == 0 || memoryTypes.Any(t => !s_derivedMemoryTypes.Contains(t)))
        {
            throw new ArgumentException(
                "Retrieval memory types must contain one or more of Fact, Procedural, or Episodic.",
                nameof(memoryTypes));
        }

        if (limit <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(limit));
        }

        if (minConfidence is < 0 or > 1)
        {
            throw new ArgumentOutOfRangeException(nameof(minConfidence));
        }
    }

    private static void ValidateUserScope(PostgresMemoryScope scope)
    {
        _ = Throw.IfNull(scope);
        if (!scope.HasUserId)
        {
            throw new ArgumentException("A non-empty UserId is required for durable memory operations.", nameof(scope));
        }
    }

    private static void ValidateThreadScope(PostgresMemoryScope scope)
    {
        ValidateUserScope(scope);
        if (!scope.HasThreadId)
        {
            throw new ArgumentException("A non-empty ThreadId is required for conversation-turn operations.", nameof(scope));
        }
    }

    private void ThrowIfDisposed() => ObjectDisposedException.ThrowIf(this._disposed, this);

    private sealed record ExtractedMemory(
        string Content,
        PostgresMemoryType MemoryType,
        double Confidence,
        double? Salience,
        IReadOnlyList<string> Tags);

    private sealed record ReconciliationDecision(long SupersededId, long WinnerId, string Reason);
}
