// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Exercises PostgreSQL and pgvector type mappings against a live database.
/// </summary>
/// <remarks>
/// Set <c>POSTGRES_MEMORY_CONNECTION_STRING</c> to run these tests.
/// </remarks>
[Trait("Category", "Postgres")]
public sealed class PostgresMemoryStoreIntegrationTests : IAsyncLifetime
{
    private readonly string _schema = $"af_memory_{Guid.NewGuid():N}";
    private NpgsqlDataSource? _dataSource;
    private PostgresMemoryStore? _store;

    public async ValueTask InitializeAsync()
    {
        var connectionString = Environment.GetEnvironmentVariable("POSTGRES_MEMORY_CONNECTION_STRING");
        if (string.IsNullOrWhiteSpace(connectionString))
        {
            return;
        }

        var builder = new NpgsqlDataSourceBuilder(connectionString);
        builder.UseVector();
        this._dataSource = builder.Build();
        this._store = new PostgresMemoryStore(
            this._dataSource,
            new PostgresMemoryClientOptions
            {
                Schema = this._schema,
                TableName = "memory",
                EmbeddingDimensions = 3,
                AutoProcess = false,
            });
        await this._store.EnsureSchemaAsync(CancellationToken.None);
    }

    public async ValueTask DisposeAsync()
    {
        if (this._dataSource is null)
        {
            return;
        }

        await this.DropSchemaAsync(this._schema);
        await this._dataSource.DisposeAsync();
    }

    [Fact]
    public async Task Store_ConcurrentSchemaInitializationWaitsForCompletionAsync()
    {
        _ = this.GetStoreOrSkip();
        var schema = $"{this._schema}_concurrent";
        var store = new PostgresMemoryStore(
            this._dataSource!,
            new PostgresMemoryClientOptions
            {
                Schema = schema,
                TableName = "memory",
                EmbeddingDimensions = 3,
                AutoProcess = false,
            });
        var scope = new PostgresMemoryScope
        {
            UserId = "user",
            ThreadId = "thread",
        };

        try
        {
            var writes = new Task<long>[16];
            for (var i = 0; i < writes.Length; i++)
            {
                writes[i] = EnsureAndInsertTurnAsync(store, scope, i);
            }

            var ids = await Task.WhenAll(writes);
            Assert.Equal(16, ids.Length);
        }
        finally
        {
            await this.DropSchemaAsync(schema);
        }
    }

    [Fact]
    public async Task Store_RoundTripsTurnsMemoriesAndHybridSearchAsync()
    {
        var store = this.GetStoreOrSkip();
        var threadScope = new PostgresMemoryScope
        {
            UserId = "user",
            ThreadId = "thread-1",
        };
        var otherThreadScope = new PostgresMemoryScope
        {
            UserId = "user",
            ThreadId = "thread-2",
        };

        var firstTurnId = await store.InsertTurnAsync(
            threadScope,
            "user",
            "I prefer PostgreSQL.",
            embedding: null,
            CancellationToken.None);
        var secondTurnId = await store.InsertTurnAsync(
            threadScope,
            "agent",
            "I will remember that.",
            embedding: null,
            CancellationToken.None);
        _ = await store.InsertTurnAsync(
            otherThreadScope,
            "user",
            "This is another thread.",
            embedding: null,
            CancellationToken.None);

        var thread = await store.GetThreadAsync(threadScope, recentK: null, CancellationToken.None);
        var recent = await store.GetThreadAsync(threadScope, recentK: 1, CancellationToken.None);
        var threadStats = await store.GetTurnStatsAfterAsync(
            threadScope,
            firstTurnId,
            includeThread: true,
            CancellationToken.None);
        var userStats = await store.GetTurnStatsAfterAsync(
            threadScope,
            0,
            includeThread: false,
            CancellationToken.None);

        Assert.Equal(2, thread.Count);
        Assert.Equal("I prefer PostgreSQL.", thread[0].Content);
        Assert.Equal(secondTurnId, recent[0].Id);
        Assert.Equal((1, secondTurnId), threadStats);
        Assert.Equal(3, userStats.Count);

        var postgresId = await store.InsertDerivedMemoryAsync(
            threadScope,
            PostgresMemoryType.Fact,
            "The user prefers PostgreSQL databases.",
            0.95,
            salience: null,
            ["database", "preference"],
            new float[] { 1, 0, 0 },
            expiresAt: null,
            CancellationToken.None);
        var proceduralId = await store.InsertDerivedMemoryAsync(
            otherThreadScope,
            PostgresMemoryType.Procedural,
            "Show SQL before the explanation.",
            0.85,
            0.7,
            Array.Empty<string>(),
            new float[] { 0, 1, 0 },
            expiresAt: null,
            CancellationToken.None);
        _ = await store.InsertDerivedMemoryAsync(
            threadScope,
            PostgresMemoryType.Episodic,
            "An expired migration event.",
            0.99,
            salience: null,
            Array.Empty<string>(),
            new float[] { 0, 0, 1 },
            DateTimeOffset.UtcNow.AddMinutes(-1),
            CancellationToken.None);
        _ = await store.InsertDerivedMemoryAsync(
            new PostgresMemoryScope
            {
                ApplicationId = "other-app",
                AgentId = "other-agent",
                UserId = "user",
                ThreadId = "thread-3",
            },
            PostgresMemoryType.Fact,
            "Memory isolated to another application.",
            0.99,
            salience: null,
            Array.Empty<string>(),
            new float[] { 1, 0, 0 },
            expiresAt: null,
            CancellationToken.None);

        var active = await store.GetActiveMemoriesAsync(
            threadScope.ToUserScope(),
            [PostgresMemoryType.Fact, PostgresMemoryType.Procedural, PostgresMemoryType.Episodic],
            10,
            0,
            CancellationToken.None);
        var duplicate = await store.FindDuplicateAsync(
            threadScope.ToUserScope(),
            PostgresMemoryType.Fact,
            ComputeContentHash("The user prefers PostgreSQL databases."),
            new float[] { 1, 0, 0 },
            0.92,
            CancellationToken.None);
        var search = await store.SearchAsync(
            threadScope.ToUserScope(),
            "PostgreSQL",
            new float[] { 1, 0, 0 },
            [PostgresMemoryType.Fact, PostgresMemoryType.Procedural],
            5,
            0.7,
            CancellationToken.None);

        Assert.Equal(2, active.Count);
        Assert.Equal(postgresId, duplicate?.Id);
        Assert.Equal(postgresId, search[0].Id);
        Assert.NotNull(search[0].Score);
        Assert.Contains("database", search[0].Tags);

        await store.MarkSupersededAsync(
            proceduralId,
            postgresId,
            "newer preference",
            CancellationToken.None);
        var remaining = await store.GetActiveMemoriesAsync(
            threadScope.ToUserScope(),
            [PostgresMemoryType.Fact, PostgresMemoryType.Procedural],
            10,
            0,
            CancellationToken.None);

        Assert.Single(remaining);
        Assert.Equal(postgresId, remaining[0].Id);
    }

    [Fact]
    public async Task Store_RoundTripsSummariesAndProcessingStateAsync()
    {
        var store = this.GetStoreOrSkip();
        var firstThread = new PostgresMemoryScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            UserId = "user",
            ThreadId = "thread-1",
        };
        var secondThread = new PostgresMemoryScope(firstThread)
        {
            ThreadId = "thread-2",
        };

        _ = await store.InsertSummaryAsync(
            firstThread,
            PostgresMemoryType.Summary,
            "First version.",
            new float[] { 1, 0, 0 },
            1,
            CancellationToken.None);
        var latestFirstThreadId = await store.InsertSummaryAsync(
            firstThread,
            PostgresMemoryType.Summary,
            "Second version.",
            new float[] { 1, 0, 0 },
            2,
            CancellationToken.None);
        var equalThreadId = await store.InsertSummaryAsync(
            firstThread,
            PostgresMemoryType.Summary,
            "Equal coverage.",
            new float[] { 1, 0, 0 },
            2,
            CancellationToken.None);
        var staleThreadId = await store.InsertSummaryAsync(
            firstThread,
            PostgresMemoryType.Summary,
            "Stale coverage.",
            new float[] { 1, 0, 0 },
            1,
            CancellationToken.None);
        var secondThreadId = await store.InsertSummaryAsync(
            secondThread,
            PostgresMemoryType.Summary,
            "Other thread.",
            new float[] { 0, 1, 0 },
            3,
            CancellationToken.None);
        var userSummaryId = await store.InsertSummaryAsync(
            firstThread.ToUserScope(),
            PostgresMemoryType.UserSummary,
            "User profile.",
            new float[] { 0, 0, 1 },
            3,
            CancellationToken.None);

        var latestThread = await store.GetLatestSummaryAsync(
            firstThread,
            PostgresMemoryType.Summary,
            CancellationToken.None);
        var latestUser = await store.GetLatestSummaryAsync(
            firstThread.ToUserScope(),
            PostgresMemoryType.UserSummary,
            CancellationToken.None);
        var recentThreads = await store.GetRecentThreadSummariesAsync(
            firstThread.ToUserScope(),
            10,
            CancellationToken.None);

        Assert.NotNull(latestFirstThreadId);
        Assert.NotNull(secondThreadId);
        Assert.NotNull(userSummaryId);
        Assert.Null(equalThreadId);
        Assert.Null(staleThreadId);
        Assert.Equal(latestFirstThreadId, latestThread.Record?.Id);
        Assert.Equal(2, latestThread.CoversThroughTurnId);
        Assert.Equal(userSummaryId, latestUser.Record?.Id);
        Assert.Equal(2, recentThreads.Count);
        Assert.Contains(recentThreads, summary => summary.Id == latestFirstThreadId);
        Assert.Contains(recentThreads, summary => summary.Id == secondThreadId);

        var concurrentInserts = new Task<long?>[8];
        for (var i = 0; i < concurrentInserts.Length; i++)
        {
            concurrentInserts[i] = store.InsertSummaryAsync(
                firstThread,
                PostgresMemoryType.Summary,
                $"Concurrent version {i}.",
                new float[] { 1, 0, 0 },
                i + 10,
                CancellationToken.None);
        }

        var concurrentIds = await Task.WhenAll(concurrentInserts);
        Assert.NotNull(concurrentIds[^1]);
        var versionCommand = this._dataSource!.CreateCommand($"""
            SELECT COUNT(*), COUNT(DISTINCT version), MAX(version), MAX(covers_through_turn_id)
            FROM "{this._schema}"."memory_summaries"
            WHERE application_id = 'app'
              AND agent_id = 'agent'
              AND user_id = 'user'
              AND thread_id = 'thread-1'
              AND summary_type = 'summary';
            """);
        await using (versionCommand.ConfigureAwait(false))
        {
            var reader = await versionCommand.ExecuteReaderAsync();
            await using (reader.ConfigureAwait(false))
            {
                Assert.True(await reader.ReadAsync());
                var count = reader.GetInt64(0);
                Assert.InRange(count, 3, 10);
                Assert.Equal(count, reader.GetInt64(1));
                Assert.Equal(count, reader.GetInt32(2));
                Assert.Equal(17, reader.GetInt64(3));
            }
        }

        var scopeKey = PostgresMemoryStore.ComputeScopeKey(firstThread, includeThread: true);
        var state = new ProcessingState(11, 12, 13, 4);
        await store.UpsertProcessingStateAsync(scopeKey, state, CancellationToken.None);
        await store.UpsertProcessingStateAsync(
            scopeKey,
            new ProcessingState(1, 20, 2, 1),
            CancellationToken.None);

        Assert.Equal(
            new ProcessingState(11, 20, 13, 4),
            await store.GetProcessingStateAsync(scopeKey, CancellationToken.None));
    }

    private PostgresMemoryStore GetStoreOrSkip()
    {
        Assert.SkipWhen(
            this._store is null,
            "Set POSTGRES_MEMORY_CONNECTION_STRING to run PostgreSQL integration tests.");
        return this._store;
    }

    private async Task DropSchemaAsync(string schema)
    {
        var command = this._dataSource!.CreateCommand($"DROP SCHEMA IF EXISTS \"{schema}\" CASCADE;");
        await using (command.ConfigureAwait(false))
        {
            await command.ExecuteNonQueryAsync();
        }
    }

    private static async Task<long> EnsureAndInsertTurnAsync(
        PostgresMemoryStore store,
        PostgresMemoryScope scope,
        int index)
    {
        await store.EnsureSchemaAsync(CancellationToken.None);
        return await store.InsertTurnAsync(
            scope,
            "user",
            $"Turn {index}",
            embedding: null,
            CancellationToken.None);
    }

    private static string ComputeContentHash(string content)
    {
        var normalized = content.Trim().ToUpperInvariant();
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(normalized)));
    }
}
