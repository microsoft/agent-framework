// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using Npgsql;
using NpgsqlTypes;
using Pgvector;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// PostgreSQL persistence primitives used by <see cref="PostgresMemoryClient"/>.
/// </summary>
internal sealed partial class PostgresMemoryStore : IPostgresMemoryStore
{
    private readonly NpgsqlDataSource _dataSource;
    private readonly string _schema;
    private readonly string _baseTableName;
    private readonly string _turnsTable;
    private readonly string _memoriesTable;
    private readonly string _summariesTable;
    private readonly string _processingTable;
    private readonly int _embeddingDimensions;
    private readonly int _reciprocalRankFusionK;
    private readonly bool _enableTurnEmbeddings;
    private readonly bool _enableAzureAiReranking;
    private readonly PostgresMemoryVectorIndexKind _vectorIndexKind;
    private readonly object _schemaSync = new();
    private Task? _ensureSchemaTask;

    public PostgresMemoryStore(NpgsqlDataSource dataSource, PostgresMemoryClientOptions options)
    {
        this._dataSource = Throw.IfNull(dataSource);
        _ = Throw.IfNull(options);

        this._schema = ValidateIdentifier(Throw.IfNullOrWhitespace(options.Schema), nameof(options.Schema), 63);
        this._baseTableName = ValidateIdentifier(Throw.IfNullOrWhitespace(options.TableName), nameof(options.TableName), 40);
        this._embeddingDimensions = options.EmbeddingDimensions is > 0 and <= 2000
            ? options.EmbeddingDimensions
            : throw new ArgumentOutOfRangeException(
                nameof(options),
                "EmbeddingDimensions must be between 1 and 2000 for the vector index.");
        this._vectorIndexKind = Enum.IsDefined(options.VectorIndexKind)
            ? options.VectorIndexKind
            : throw new ArgumentOutOfRangeException(nameof(options), "VectorIndexKind must be a defined value.");
        this._reciprocalRankFusionK = options.ReciprocalRankFusionK > 0
            ? options.ReciprocalRankFusionK
            : throw new ArgumentOutOfRangeException(nameof(options), "ReciprocalRankFusionK must be greater than zero.");
        this._enableTurnEmbeddings = options.EnableTurnEmbeddings;
        this._enableAzureAiReranking = options.EnableAzureAiReranking;

        this._turnsTable = this.Qualify($"{this._baseTableName}_turns");
        this._memoriesTable = this.Qualify($"{this._baseTableName}_memories");
        this._summariesTable = this.Qualify($"{this._baseTableName}_summaries");
        this._processingTable = this.Qualify($"{this._baseTableName}_processing");
    }

    public Task EnsureSchemaAsync(CancellationToken cancellationToken)
    {
        Task ensureSchemaTask;
        lock (this._schemaSync)
        {
            ensureSchemaTask = this._ensureSchemaTask ??= this.EnsureSchemaCoreAsync();
        }

        return ensureSchemaTask.WaitAsync(cancellationToken);
    }

    private async Task EnsureSchemaCoreAsync()
    {
        var turnVectorIndexSql = this._enableTurnEmbeddings
            ? this.GetVectorIndexSql(this._turnsTable, $"ix_{this._baseTableName}_turns_embedding", $"ix_{this._baseTableName}_turns_diskann")
            : string.Empty;
        var memoryVectorIndexSql = this.GetVectorIndexSql(
            this._memoriesTable,
            $"ix_{this._baseTableName}_memories_embedding",
            $"ix_{this._baseTableName}_memories_diskann");
        var vectorIndexExtensionSql = this._vectorIndexKind == PostgresMemoryVectorIndexKind.DiskAnn
            ? "CREATE EXTENSION IF NOT EXISTS pg_diskann;"
            : string.Empty;
        var rerankingExtensionSql = this._enableAzureAiReranking
            ? "CREATE EXTENSION IF NOT EXISTS azure_ai;"
            : string.Empty;

        var sql = $"""
            CREATE EXTENSION IF NOT EXISTS vector;
            {vectorIndexExtensionSql}
            {rerankingExtensionSql}
            CREATE SCHEMA IF NOT EXISTS "{this._schema}";

            CREATE TABLE IF NOT EXISTS {this._turnsTable} (
                id BIGSERIAL PRIMARY KEY,
                application_id TEXT,
                agent_id TEXT,
                user_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({this._embeddingDimensions}),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_{this._baseTableName}_turns_scope
                ON {this._turnsTable} (application_id, agent_id, user_id, thread_id, id);
            {turnVectorIndexSql}

            CREATE TABLE IF NOT EXISTS {this._memoriesTable} (
                id BIGSERIAL PRIMARY KEY,
                application_id TEXT,
                agent_id TEXT,
                user_id TEXT NOT NULL,
                thread_id TEXT,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                salience DOUBLE PRECISION,
                tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                embedding vector({this._embeddingDimensions}) NOT NULL,
                content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
                content_hash CHAR(64) NOT NULL,
                is_superseded BOOLEAN NOT NULL DEFAULT FALSE,
                superseded_by BIGINT,
                supersede_reason TEXT,
                expires_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_{this._baseTableName}_memories_scope
                ON {this._memoriesTable} (application_id, agent_id, user_id, thread_id, memory_type);
            CREATE INDEX IF NOT EXISTS ix_{this._baseTableName}_memories_hash
                ON {this._memoriesTable} (application_id, agent_id, user_id, memory_type, content_hash);
            CREATE INDEX IF NOT EXISTS ix_{this._baseTableName}_memories_tsv
                ON {this._memoriesTable} USING gin (content_tsv);
            {memoryVectorIndexSql}

            CREATE TABLE IF NOT EXISTS {this._summariesTable} (
                id BIGSERIAL PRIMARY KEY,
                application_id TEXT,
                agent_id TEXT,
                user_id TEXT NOT NULL,
                thread_id TEXT,
                summary_type TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding vector({this._embeddingDimensions}) NOT NULL,
                covers_through_turn_id BIGINT NOT NULL DEFAULT 0,
                version INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS ix_{this._baseTableName}_summaries_scope
                ON {this._summariesTable} (application_id, agent_id, user_id, thread_id, summary_type, version DESC);

            CREATE TABLE IF NOT EXISTS {this._processingTable} (
                scope_key CHAR(64) PRIMARY KEY,
                fact_through_turn_id BIGINT NOT NULL DEFAULT 0,
                summary_through_turn_id BIGINT NOT NULL DEFAULT 0,
                user_summary_through_turn_id BIGINT NOT NULL DEFAULT 0,
                extraction_runs INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """;

        FeatureUsageMarker.MarkUsed();
        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            try
            {
                await command.ExecuteNonQueryAsync(CancellationToken.None).ConfigureAwait(false);
                await this._dataSource.ReloadTypesAsync(CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                lock (this._schemaSync)
                {
                    this._ensureSchemaTask = null;
                }

                throw;
            }
        }
    }

    internal string GetVectorIndexSql(string table, string hnswIndexName, string diskAnnIndexName)
    {
        var hnswIndex = this.Qualify(hnswIndexName);
        var diskAnnIndex = this.Qualify(diskAnnIndexName);

        return this._vectorIndexKind switch
        {
            PostgresMemoryVectorIndexKind.Hnsw => $"""
                DROP INDEX IF EXISTS {diskAnnIndex};
                CREATE INDEX IF NOT EXISTS {hnswIndexName} ON {table} USING hnsw (embedding vector_cosine_ops);
                """,
            PostgresMemoryVectorIndexKind.DiskAnn => $"""
                DROP INDEX IF EXISTS {hnswIndex};
                CREATE INDEX IF NOT EXISTS {diskAnnIndexName} ON {table} USING diskann (embedding vector_cosine_ops);
                """,
            _ => throw new InvalidOperationException("The vector index kind is not supported."),
        };
    }

    public async Task<long> InsertTurnAsync(
        PostgresMemoryScope scope,
        string role,
        string content,
        ReadOnlyMemory<float>? embedding,
        CancellationToken cancellationToken)
    {
        var columns = embedding.HasValue
            ? "application_id, agent_id, user_id, thread_id, role, content, embedding"
            : "application_id, agent_id, user_id, thread_id, role, content";
        var values = embedding.HasValue
            ? "@application_id, @agent_id, @user_id, @thread_id, @role, @content, @embedding"
            : "@application_id, @agent_id, @user_id, @thread_id, @role, @content";

        var sql = $"""
            INSERT INTO {this._turnsTable} ({columns})
            VALUES ({values})
            RETURNING id;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            command.Parameters.AddWithValue("role", role);
            command.Parameters.AddWithValue("content", content);
            if (embedding.HasValue)
            {
                command.Parameters.AddWithValue("embedding", new Vector(embedding.Value));
            }

            var id = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
            return Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture);
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetThreadAsync(
        PostgresMemoryScope scope,
        int? recentK,
        CancellationToken cancellationToken)
    {
        var limitSql = recentK.HasValue ? "LIMIT @recent_k" : string.Empty;
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
            FROM (
                SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
                FROM {this._turnsTable}
                WHERE {StrictThreadScopeSql}
                ORDER BY id DESC
                {limitSql}
            ) turns
            ORDER BY id ASC;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            if (recentK.HasValue)
            {
                command.Parameters.AddWithValue("recent_k", recentK.Value);
            }

            var results = new List<PostgresMemoryRecord>();
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(ReadTurn(reader));
                }
            }

            return results;
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetTurnsAfterAsync(
        PostgresMemoryScope scope,
        long afterTurnId,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, role, content, created_at
            FROM {this._turnsTable}
            WHERE {StrictThreadScopeSql} AND id > @after_turn_id
            ORDER BY id ASC;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            command.Parameters.AddWithValue("after_turn_id", afterTurnId);

            var results = new List<PostgresMemoryRecord>();
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(ReadTurn(reader));
                }
            }

            return results;
        }
    }

    public async Task<(int Count, long LatestTurnId)> GetTurnStatsAfterAsync(
        PostgresMemoryScope scope,
        long afterTurnId,
        bool includeThread,
        CancellationToken cancellationToken)
    {
        var filter = includeThread ? StrictThreadScopeSql : StrictUserScopeSql;
        var sql = $"""
            SELECT COUNT(*), COALESCE(MAX(id), 0)
            FROM {this._turnsTable}
            WHERE {filter} AND id > @after_turn_id;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread);
            command.Parameters.AddWithValue("after_turn_id", afterTurnId);

            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                _ = await reader.ReadAsync(cancellationToken).ConfigureAwait(false);
                return (checked((int)reader.GetInt64(0)), reader.GetInt64(1));
            }
        }
    }

    public async Task<PostgresMemoryRecord?> FindDuplicateAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType memoryType,
        string contentHash,
        ReadOnlyMemory<float> embedding,
        double similarityThreshold,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, memory_type, content,
                   confidence, salience, tags, created_at, updated_at, is_superseded,
                   superseded_by, supersede_reason,
                   1.0 - (embedding <=> @embedding) AS score
            FROM {this._memoriesTable}
            WHERE {StrictUserScopeSql}
              AND memory_type = @memory_type
              AND is_superseded = FALSE
              AND (expires_at IS NULL OR expires_at > now())
              AND (content_hash = @content_hash OR (1.0 - (embedding <=> @embedding)) >= @threshold)
            ORDER BY (content_hash = @content_hash) DESC, score DESC
            LIMIT 1;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: false);
            command.Parameters.AddWithValue("memory_type", ToStoreValue(memoryType));
            command.Parameters.AddWithValue("content_hash", contentHash);
            command.Parameters.AddWithValue("embedding", new Vector(embedding));
            command.Parameters.AddWithValue("threshold", similarityThreshold);

            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                return await reader.ReadAsync(cancellationToken).ConfigureAwait(false)
                    ? ReadDerivedMemory(reader, scoreOrdinal: 15)
                    : null;
            }
        }
    }

    public async Task<long> InsertDerivedMemoryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType memoryType,
        string content,
        double confidence,
        double? salience,
        IReadOnlyList<string> tags,
        ReadOnlyMemory<float> embedding,
        DateTimeOffset? expiresAt,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            INSERT INTO {this._memoriesTable}
                (application_id, agent_id, user_id, thread_id, memory_type, content, confidence,
                 salience, tags, embedding, content_hash, expires_at)
            VALUES
                (@application_id, @agent_id, @user_id, @thread_id, @memory_type, @content, @confidence,
                 @salience, @tags, @embedding, @content_hash, @expires_at)
            RETURNING id;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            command.Parameters.AddWithValue("memory_type", ToStoreValue(memoryType));
            command.Parameters.AddWithValue("content", content);
            command.Parameters.AddWithValue("confidence", confidence);
            AddNullableParameter(command, "salience", NpgsqlDbType.Double, salience);
            command.Parameters.AddWithValue("tags", AsArray(tags));
            command.Parameters.AddWithValue("embedding", new Vector(embedding));
            command.Parameters.AddWithValue("content_hash", ComputeContentHash(content));
            AddNullableParameter(command, "expires_at", NpgsqlDbType.TimestampTz, expiresAt);

            var id = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
            return Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture);
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetActiveMemoriesAsync(
        PostgresMemoryScope scope,
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int limit,
        double minConfidence,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, memory_type, content,
                   confidence, salience, tags, created_at, updated_at, is_superseded,
                   superseded_by, supersede_reason
            FROM {this._memoriesTable}
            WHERE {RetrievalScopeSql}
              AND memory_type = ANY(@memory_types)
              AND confidence >= @min_confidence
              AND is_superseded = FALSE
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC
            LIMIT @limit;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            command.Parameters.AddWithValue("memory_types", ToStoreValues(memoryTypes));
            command.Parameters.AddWithValue("min_confidence", minConfidence);
            command.Parameters.AddWithValue("limit", limit);

            var results = new List<PostgresMemoryRecord>();
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(ReadDerivedMemory(reader));
                }
            }

            return results;
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRecord>> SearchAsync(
        PostgresMemoryScope scope,
        string searchTerms,
        ReadOnlyMemory<float> queryEmbedding,
        IReadOnlyList<PostgresMemoryType> memoryTypes,
        int topK,
        double minConfidence,
        CancellationToken cancellationToken)
    {
        var candidateLimit = Math.Max(topK * 5, topK);
        var sql = $"""
            WITH eligible AS (
                SELECT *
                FROM {this._memoriesTable}
                WHERE {RetrievalScopeSql}
                  AND memory_type = ANY(@memory_types)
                  AND confidence >= @min_confidence
                  AND is_superseded = FALSE
                  AND (expires_at IS NULL OR expires_at > now())
            ),
            vector_ranked AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> @query_embedding) AS rnk
                FROM eligible
                ORDER BY embedding <=> @query_embedding
                LIMIT @candidate_limit
            ),
            text_ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY ts_rank(content_tsv, plainto_tsquery('english', @query_text)) DESC) AS rnk
                FROM eligible
                WHERE content_tsv @@ plainto_tsquery('english', @query_text)
                ORDER BY ts_rank(content_tsv, plainto_tsquery('english', @query_text)) DESC
                LIMIT @candidate_limit
            ),
            fused AS (
                SELECT COALESCE(v.id, t.id) AS id,
                       COALESCE(1.0::double precision / (@rrf_k + v.rnk), 0) +
                       COALESCE(1.0::double precision / (@rrf_k + t.rnk), 0) AS score
                FROM vector_ranked v
                FULL OUTER JOIN text_ranked t ON v.id = t.id
            )
            SELECT e.id, e.application_id, e.agent_id, e.user_id, e.thread_id, e.memory_type,
                   e.content, e.confidence, e.salience, e.tags, e.created_at, e.updated_at,
                   e.is_superseded, e.superseded_by, e.supersede_reason, f.score
            FROM fused f
            JOIN eligible e ON e.id = f.id
            ORDER BY f.score DESC
            LIMIT @top_k;
            """;

        FeatureUsageMarker.MarkUsed();
        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: true);
            command.Parameters.AddWithValue("memory_types", ToStoreValues(memoryTypes));
            command.Parameters.AddWithValue("min_confidence", minConfidence);
            command.Parameters.AddWithValue("query_embedding", new Vector(queryEmbedding));
            command.Parameters.AddWithValue("query_text", searchTerms);
            command.Parameters.AddWithValue("candidate_limit", candidateLimit);
            command.Parameters.AddWithValue("rrf_k", this._reciprocalRankFusionK);
            command.Parameters.AddWithValue("top_k", topK);

            var results = new List<PostgresMemoryRecord>(topK);
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(ReadDerivedMemory(reader, scoreOrdinal: 15));
                }
            }

            return results;
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRerankResult>> RerankAsync(
        string searchTerms,
        IReadOnlyList<PostgresMemoryRecord> candidates,
        string model,
        CancellationToken cancellationToken)
    {
        if (candidates.Count == 0)
        {
            return [];
        }

        const string Sql = """
            SELECT document_id, rank, relevance_score
            FROM azure_ai.rank(
                query => @query_text,
                document_contents => @document_contents,
                document_ids => @document_ids,
                model => @model)
            ORDER BY rank;
            """;

        var command = this._dataSource.CreateCommand(Sql);
        await using (command.ConfigureAwait(false))
        {
            command.Parameters.AddWithValue("query_text", NpgsqlDbType.Text, searchTerms);
            command.Parameters.AddWithValue(
                "document_contents",
                NpgsqlDbType.Array | NpgsqlDbType.Text,
                candidates.Select(candidate => candidate.Content).ToArray());
            command.Parameters.AddWithValue(
                "document_ids",
                NpgsqlDbType.Array | NpgsqlDbType.Text,
                candidates.Select(candidate => candidate.Id.ToString(System.Globalization.CultureInfo.InvariantCulture)).ToArray());
            command.Parameters.AddWithValue("model", NpgsqlDbType.Text, model);

            var results = new List<PostgresMemoryRerankResult>(candidates.Count);
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    var id = long.Parse(reader.GetString(0), System.Globalization.CultureInfo.InvariantCulture);
                    var rank = Convert.ToInt32(reader.GetValue(1), System.Globalization.CultureInfo.InvariantCulture);
                    var relevanceScore = Convert.ToDouble(reader.GetValue(2), System.Globalization.CultureInfo.InvariantCulture);
                    results.Add(new PostgresMemoryRerankResult(id, rank, relevanceScore));
                }
            }

            return results;
        }
    }

    public async Task MarkSupersededAsync(
        long supersededId,
        long winnerId,
        string reason,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            UPDATE {this._memoriesTable}
            SET is_superseded = TRUE,
                superseded_by = @winner_id,
                supersede_reason = @reason,
                updated_at = now()
            WHERE id = @superseded_id AND is_superseded = FALSE;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            command.Parameters.AddWithValue("superseded_id", supersededId);
            command.Parameters.AddWithValue("winner_id", winnerId);
            command.Parameters.AddWithValue("reason", reason);
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    public async Task<(PostgresMemoryRecord? Record, long CoversThroughTurnId)> GetLatestSummaryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType summaryType,
        CancellationToken cancellationToken)
    {
        var includeThread = summaryType == PostgresMemoryType.Summary;
        var filter = includeThread ? StrictThreadScopeSql : StrictUserScopeSql;
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, summary_type, content,
                   covers_through_turn_id, created_at, updated_at
            FROM {this._summariesTable}
            WHERE {filter} AND summary_type = @summary_type
            ORDER BY version DESC
            LIMIT 1;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread);
            command.Parameters.AddWithValue("summary_type", ToStoreValue(summaryType));

            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                if (!await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    return (null, 0);
                }

                var record = new PostgresMemoryRecord
                {
                    Id = reader.GetInt64(0),
                    ApplicationId = reader.IsDBNull(1) ? null : reader.GetString(1),
                    AgentId = reader.IsDBNull(2) ? null : reader.GetString(2),
                    UserId = reader.GetString(3),
                    ThreadId = reader.IsDBNull(4) ? null : reader.GetString(4),
                    MemoryType = FromStoreValue(reader.GetString(5)),
                    Content = reader.GetString(6),
                    CreatedAt = ReadTimestamp(reader, 8),
                    UpdatedAt = ReadTimestamp(reader, 9),
                };

                return (record, reader.GetInt64(7));
            }
        }
    }

    public async Task<long?> InsertSummaryAsync(
        PostgresMemoryScope scope,
        PostgresMemoryType summaryType,
        string content,
        ReadOnlyMemory<float> embedding,
        long coversThroughTurnId,
        CancellationToken cancellationToken)
    {
        var includeThread = summaryType == PostgresMemoryType.Summary;
        var filter = includeThread ? StrictThreadScopeSql : StrictUserScopeSql;
        var scopeKey = $"{ComputeScopeKey(scope, includeThread)}:{ToStoreValue(summaryType)}";
        var sql = $"""
            INSERT INTO {this._summariesTable}
                (application_id, agent_id, user_id, thread_id, summary_type, content,
                 embedding, covers_through_turn_id, version)
            SELECT @application_id, @agent_id, @user_id, @thread_id, @summary_type, @content,
                   @embedding, @covers_through_turn_id,
                   COALESCE(MAX(version), 0) + 1
            FROM {this._summariesTable}
            WHERE {filter} AND summary_type = @summary_type
            HAVING COALESCE(MAX(covers_through_turn_id), 0) < @covers_through_turn_id
            RETURNING id;
            """;

        var connection = await this._dataSource.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
            await using (transaction.ConfigureAwait(false))
            {
                var lockCommand = connection.CreateCommand();
                await using (lockCommand.ConfigureAwait(false))
                {
                    lockCommand.Transaction = transaction;
                    lockCommand.CommandText =
                        "SELECT pg_advisory_xact_lock(hashtextextended(@scope_key, 0));";
                    lockCommand.Parameters.AddWithValue("scope_key", scopeKey);
                    await lockCommand.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
                }

                var command = connection.CreateCommand();
                await using (command.ConfigureAwait(false))
                {
                    command.Transaction = transaction;
#pragma warning disable CA2100 // Schema and table identifiers were validated; all record values are parameters.
                    command.CommandText = sql;
#pragma warning restore CA2100
                    AddScopeParameters(command, scope, includeThread: true);
                    command.Parameters.AddWithValue("summary_type", ToStoreValue(summaryType));
                    command.Parameters.AddWithValue("content", content);
                    command.Parameters.AddWithValue("embedding", new Vector(embedding));
                    command.Parameters.AddWithValue("covers_through_turn_id", coversThroughTurnId);

                    var id = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
                    await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
                    return id is null or DBNull
                        ? null
                        : Convert.ToInt64(id, System.Globalization.CultureInfo.InvariantCulture);
                }
            }
        }
    }

    public async Task<IReadOnlyList<PostgresMemoryRecord>> GetRecentThreadSummariesAsync(
        PostgresMemoryScope scope,
        int limit,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT id, application_id, agent_id, user_id, thread_id, summary_type, content,
                   covers_through_turn_id, created_at, updated_at
            FROM (
                SELECT DISTINCT ON (thread_id)
                       id, application_id, agent_id, user_id, thread_id, summary_type, content,
                       covers_through_turn_id, created_at, updated_at, version
                FROM {this._summariesTable}
                WHERE {StrictUserScopeSql} AND summary_type = 'summary'
                ORDER BY thread_id, version DESC
            ) latest
            ORDER BY updated_at DESC
            LIMIT @limit;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            AddScopeParameters(command, scope, includeThread: false);
            command.Parameters.AddWithValue("limit", limit);

            var results = new List<PostgresMemoryRecord>();
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
                {
                    results.Add(new PostgresMemoryRecord
                    {
                        Id = reader.GetInt64(0),
                        ApplicationId = reader.IsDBNull(1) ? null : reader.GetString(1),
                        AgentId = reader.IsDBNull(2) ? null : reader.GetString(2),
                        UserId = reader.GetString(3),
                        ThreadId = reader.IsDBNull(4) ? null : reader.GetString(4),
                        MemoryType = FromStoreValue(reader.GetString(5)),
                        Content = reader.GetString(6),
                        CreatedAt = ReadTimestamp(reader, 8),
                        UpdatedAt = ReadTimestamp(reader, 9),
                    });
                }
            }

            return results;
        }
    }

    public async Task<ProcessingState> GetProcessingStateAsync(string scopeKey, CancellationToken cancellationToken)
    {
        var sql = $"""
            SELECT fact_through_turn_id, summary_through_turn_id,
                   user_summary_through_turn_id, extraction_runs
            FROM {this._processingTable}
            WHERE scope_key = @scope_key;
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            command.Parameters.AddWithValue("scope_key", scopeKey);
            var reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                return await reader.ReadAsync(cancellationToken).ConfigureAwait(false)
                    ? new ProcessingState(reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2), reader.GetInt32(3))
                    : default;
            }
        }
    }

    public async Task UpsertProcessingStateAsync(
        string scopeKey,
        ProcessingState state,
        CancellationToken cancellationToken)
    {
        var sql = $"""
            INSERT INTO {this._processingTable} AS current
                (scope_key, fact_through_turn_id, summary_through_turn_id,
                 user_summary_through_turn_id, extraction_runs, updated_at)
            VALUES
                (@scope_key, @fact_through_turn_id, @summary_through_turn_id,
                 @user_summary_through_turn_id, @extraction_runs, now())
            ON CONFLICT (scope_key) DO UPDATE SET
                fact_through_turn_id = GREATEST(
                    current.fact_through_turn_id,
                    EXCLUDED.fact_through_turn_id),
                summary_through_turn_id = GREATEST(
                    current.summary_through_turn_id,
                    EXCLUDED.summary_through_turn_id),
                user_summary_through_turn_id = GREATEST(
                    current.user_summary_through_turn_id,
                    EXCLUDED.user_summary_through_turn_id),
                extraction_runs = GREATEST(
                    current.extraction_runs,
                    EXCLUDED.extraction_runs),
                updated_at = now();
            """;

        var command = this._dataSource.CreateCommand(sql);
        await using (command.ConfigureAwait(false))
        {
            command.Parameters.AddWithValue("scope_key", scopeKey);
            command.Parameters.AddWithValue("fact_through_turn_id", state.FactThroughTurnId);
            command.Parameters.AddWithValue("summary_through_turn_id", state.SummaryThroughTurnId);
            command.Parameters.AddWithValue("user_summary_through_turn_id", state.UserSummaryThroughTurnId);
            command.Parameters.AddWithValue("extraction_runs", state.ExtractionRuns);
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }
    }

    public static string ComputeScopeKey(PostgresMemoryScope scope, bool includeThread)
    {
        var input = new StringBuilder();
        AppendScopeComponent(input, scope.ApplicationId);
        AppendScopeComponent(input, scope.AgentId);
        AppendScopeComponent(input, scope.UserId);
        AppendScopeComponent(input, includeThread ? scope.ThreadId : null);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(input.ToString())));
    }

    private static void AppendScopeComponent(StringBuilder builder, string? value)
    {
        value ??= string.Empty;
        _ = builder.Append(Encoding.UTF8.GetByteCount(value)).Append(':').Append(value);
    }

    private string Qualify(string tableName) => $"\"{this._schema}\".\"{tableName}\"";

    private static PostgresMemoryRecord ReadTurn(NpgsqlDataReader reader) =>
        new()
        {
            Id = reader.GetInt64(0),
            ApplicationId = reader.IsDBNull(1) ? null : reader.GetString(1),
            AgentId = reader.IsDBNull(2) ? null : reader.GetString(2),
            UserId = reader.GetString(3),
            ThreadId = reader.GetString(4),
            Role = reader.GetString(5),
            Content = reader.GetString(6),
            MemoryType = PostgresMemoryType.Turn,
            CreatedAt = ReadTimestamp(reader, 7),
            UpdatedAt = ReadTimestamp(reader, 7),
        };

    private static PostgresMemoryRecord ReadDerivedMemory(NpgsqlDataReader reader, int? scoreOrdinal = null) =>
        new()
        {
            Id = reader.GetInt64(0),
            ApplicationId = reader.IsDBNull(1) ? null : reader.GetString(1),
            AgentId = reader.IsDBNull(2) ? null : reader.GetString(2),
            UserId = reader.GetString(3),
            ThreadId = reader.IsDBNull(4) ? null : reader.GetString(4),
            MemoryType = FromStoreValue(reader.GetString(5)),
            Content = reader.GetString(6),
            Confidence = reader.GetDouble(7),
            Salience = reader.IsDBNull(8) ? null : reader.GetDouble(8),
            Tags = reader.GetFieldValue<string[]>(9),
            CreatedAt = ReadTimestamp(reader, 10),
            UpdatedAt = ReadTimestamp(reader, 11),
            IsSuperseded = reader.GetBoolean(12),
            SupersededBy = reader.IsDBNull(13) ? null : reader.GetInt64(13),
            SupersedeReason = reader.IsDBNull(14) ? null : reader.GetString(14),
            Score = scoreOrdinal.HasValue && !reader.IsDBNull(scoreOrdinal.Value)
                ? reader.GetDouble(scoreOrdinal.Value)
                : null,
        };

    private static DateTimeOffset ReadTimestamp(NpgsqlDataReader reader, int ordinal) =>
        new(reader.GetFieldValue<DateTime>(ordinal));

    private static void AddScopeParameters(NpgsqlCommand command, PostgresMemoryScope scope, bool includeThread)
    {
        AddNullableParameter(command, "application_id", NpgsqlDbType.Text, scope.ApplicationId);
        AddNullableParameter(command, "agent_id", NpgsqlDbType.Text, scope.AgentId);
        command.Parameters.AddWithValue("user_id", scope.UserId!);
        if (includeThread)
        {
            AddNullableParameter(command, "thread_id", NpgsqlDbType.Text, scope.ThreadId);
        }
    }

    private static void AddNullableParameter(
        NpgsqlCommand command,
        string name,
        NpgsqlDbType type,
        object? value)
    {
        var parameter = command.Parameters.Add(name, type);
        parameter.Value = value ?? DBNull.Value;
    }

    private static string ComputeContentHash(string content)
    {
        var normalized = content.Trim().ToUpperInvariant();
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(normalized)));
    }

    private static string[] AsArray(IReadOnlyList<string> values)
    {
        if (values is string[] array)
        {
            return array;
        }

        var result = new string[values.Count];
        for (var i = 0; i < values.Count; i++)
        {
            result[i] = values[i];
        }

        return result;
    }

    private static string[] ToStoreValues(IReadOnlyList<PostgresMemoryType> memoryTypes)
    {
        var result = new string[memoryTypes.Count];
        for (var i = 0; i < memoryTypes.Count; i++)
        {
            result[i] = ToStoreValue(memoryTypes[i]);
        }

        return result;
    }

    internal static string ToStoreValue(PostgresMemoryType memoryType) =>
        memoryType switch
        {
            PostgresMemoryType.Turn => "turn",
            PostgresMemoryType.Fact => "fact",
            PostgresMemoryType.Procedural => "procedural",
            PostgresMemoryType.Episodic => "episodic",
            PostgresMemoryType.Summary => "summary",
            PostgresMemoryType.UserSummary => "user_summary",
            _ => throw new ArgumentOutOfRangeException(nameof(memoryType)),
        };

    internal static PostgresMemoryType FromStoreValue(string memoryType) =>
        memoryType switch
        {
            "turn" => PostgresMemoryType.Turn,
            "fact" => PostgresMemoryType.Fact,
            "procedural" => PostgresMemoryType.Procedural,
            "episodic" => PostgresMemoryType.Episodic,
            "summary" => PostgresMemoryType.Summary,
            "user_summary" => PostgresMemoryType.UserSummary,
            _ => throw new ArgumentException($"Unknown PostgreSQL memory type '{memoryType}'.", nameof(memoryType)),
        };

    private static string ValidateIdentifier(string identifier, string parameterName, int maximumLength)
    {
        if (identifier.Length > maximumLength || !IdentifierRegex().IsMatch(identifier))
        {
            throw new ArgumentException(
                $"'{identifier}' is not a valid PostgreSQL identifier. Use at most {maximumLength} letters, digits, or underscores, and do not start with a digit.",
                parameterName);
        }

        return identifier;
    }

    private const string StrictUserScopeSql =
        "application_id IS NOT DISTINCT FROM @application_id " +
        "AND agent_id IS NOT DISTINCT FROM @agent_id " +
        "AND user_id = @user_id";

    private const string StrictThreadScopeSql =
        "application_id IS NOT DISTINCT FROM @application_id " +
        "AND agent_id IS NOT DISTINCT FROM @agent_id " +
        "AND user_id = @user_id " +
        "AND thread_id IS NOT DISTINCT FROM @thread_id";

    private const string RetrievalScopeSql =
        "application_id IS NOT DISTINCT FROM @application_id " +
        "AND agent_id IS NOT DISTINCT FROM @agent_id " +
        "AND user_id = @user_id " +
        "AND (@thread_id IS NULL OR thread_id IS NOT DISTINCT FROM @thread_id)";

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_]*$")]
    private static partial Regex IdentifierRegex();
}

/// <summary>
/// Processing checkpoints for one memory scope.
/// </summary>
internal readonly record struct ProcessingState(
    long FactThroughTurnId,
    long SummaryThroughTurnId,
    long UserSummaryThroughTurnId,
    int ExtractionRuns);
