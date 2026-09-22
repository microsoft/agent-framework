// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Shared.Diagnostics;
using Npgsql;
using NpgsqlTypes;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Stores workflow checkpoints in PostgreSQL, isolated by application, tenant, and workflow session.
/// </summary>
/// <remarks>
/// The supplied data source remains caller-owned. Call <see cref="EnsureTableAsync"/> before first use.
/// No vector extension is required. This store persists checkpoints but does not schedule workflow recovery
/// or guarantee exactly-once execution of external side effects. Only load checkpoints from trusted storage.
/// </remarks>
public sealed partial class PostgresCheckpointStore : JsonCheckpointStore
{
    private const string PayloadFormat = "agent-framework.dotnet.checkpoint.v1";
    private readonly NpgsqlDataSource _dataSource;
    private readonly string _applicationId;
    private readonly string _tenantId;
    private readonly string _table;
    private readonly string _index;

    /// <summary>
    /// Initializes a PostgreSQL checkpoint store with trusted application and tenant scope identifiers.
    /// </summary>
    /// <param name="dataSource">The caller-owned PostgreSQL data source.</param>
    /// <param name="applicationId">The application that owns the workflow sessions.</param>
    /// <param name="tenantId">The authenticated tenant or user isolation boundary.</param>
    /// <param name="schema">An existing PostgreSQL schema.</param>
    /// <param name="tableName">The checkpoint table, which can also be shared with the Python provider.</param>
    public PostgresCheckpointStore(
        NpgsqlDataSource dataSource,
        string applicationId,
        string tenantId,
        string schema = "public",
        string tableName = "agent_framework_checkpoints")
    {
        this._dataSource = Throw.IfNull(dataSource);
        this._applicationId = ValidateScope(applicationId, nameof(applicationId));
        this._tenantId = ValidateScope(tenantId, nameof(tenantId));
        this._table = $"{QuoteIdentifier(schema, nameof(schema))}.{QuoteIdentifier(tableName, nameof(tableName))}";
        var digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(this._table)))[..16];
        this._index = $"\"af_checkpoint_scope_{digest}\"";
    }

    /// <summary>
    /// Creates a checkpoint manager that accepts the property ordering used by PostgreSQL JSONB.
    /// </summary>
    /// <param name="customOptions">Optional serializer settings and contracts for application-defined state types.
    /// The supplied options are copied, not modified.</param>
    /// <returns>A JSON checkpoint manager configured for this store.</returns>
    public CheckpointManager CreateCheckpointManager(JsonSerializerOptions? customOptions = null)
    {
        var options = customOptions is null ? new JsonSerializerOptions() : new JsonSerializerOptions(customOptions);
        options.AllowOutOfOrderMetadataProperties = true;
        return CheckpointManager.CreateJson(this, options);
    }

    /// <summary>
    /// Creates the checkpoint table and history index when absent. Does not create schemas, install
    /// extensions, or migrate incompatible existing tables.
    /// </summary>
    /// <param name="cancellationToken">A token used to cancel the operation.</param>
    /// <returns>A task representing the initialization operation.</returns>
    [SuppressMessage("Security", "CA2100:Review SQL queries for security vulnerabilities", Justification = "Only identifiers quoted by NpgsqlCommandBuilder are interpolated; no data values are included in the SQL text.")]
    public async Task EnsureTableAsync(CancellationToken cancellationToken = default)
    {
        FeatureUsageMarker.MarkUsed();
        var connection = await this._dataSource.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
            await using (transaction.ConfigureAwait(false))
            {
                var command = connection.CreateCommand();
                await using (command.ConfigureAwait(false))
                {
                    command.Transaction = transaction;
                    command.CommandText = $"""
                        CREATE TABLE IF NOT EXISTS {this._table} (
                            application_id TEXT NOT NULL,
                            tenant_id TEXT NOT NULL,
                            run_id TEXT NOT NULL,
                            payload_format TEXT NOT NULL,
                            checkpoint_id TEXT NOT NULL,
                            workflow_name TEXT,
                            parent_checkpoint_id TEXT,
                            version INTEGER NOT NULL DEFAULT 1,
                            sequence BIGINT GENERATED ALWAYS AS IDENTITY,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                            payload JSONB NOT NULL,
                            PRIMARY KEY (application_id, tenant_id, run_id, payload_format, checkpoint_id)
                        );
                        CREATE INDEX IF NOT EXISTS {this._index} ON {this._table}
                            (application_id, tenant_id, run_id, payload_format, sequence);
                        """;
                    await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
                }

                await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <inheritdoc/>
    [SuppressMessage("Security", "CA2100:Review SQL queries for security vulnerabilities", Justification = "Only identifiers quoted by NpgsqlCommandBuilder are interpolated; all data values use parameters.")]
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(
        string sessionId,
        JsonElement value,
        CheckpointInfo? parent = null)
    {
        ValidateSession(sessionId, parent, nameof(parent));
        if (value.ValueKind == JsonValueKind.Undefined)
        {
            throw new ArgumentException("Checkpoint value must contain JSON.", nameof(value));
        }

        FeatureUsageMarker.MarkUsed();
        var checkpointId = Guid.NewGuid().ToString("N");
        var payload = value.GetRawText();
        var lockScope = this.CreateLockScope(sessionId);
        var connection = await this._dataSource.OpenConnectionAsync().ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            var transaction = await connection.BeginTransactionAsync().ConfigureAwait(false);
            await using (transaction.ConfigureAwait(false))
            {
                var command = connection.CreateCommand();
                await using (command.ConfigureAwait(false))
                {
                    command.Transaction = transaction;
                    command.CommandText = "SELECT pg_advisory_xact_lock(hashtextextended(@lock_scope, 0));";
                    command.Parameters.AddWithValue("lock_scope", NpgsqlDbType.Text, lockScope);
                    await command.ExecuteNonQueryAsync().ConfigureAwait(false);

                    command.Parameters.Clear();
                    command.CommandText = $"""
                        INSERT INTO {this._table}
                            (application_id, tenant_id, run_id, payload_format, checkpoint_id, parent_checkpoint_id, payload)
                        VALUES (@application_id, @tenant_id, @run_id, @payload_format, @checkpoint_id, @parent_checkpoint_id, @payload);
                        """;
                    this.AddScopeParameters(command, sessionId);
                    command.Parameters.AddWithValue("checkpoint_id", checkpointId);
                    command.Parameters.AddWithValue("parent_checkpoint_id", NpgsqlDbType.Text, (object?)parent?.CheckpointId ?? DBNull.Value);
                    command.Parameters.AddWithValue("payload", NpgsqlDbType.Jsonb, payload);
                    await command.ExecuteNonQueryAsync().ConfigureAwait(false);
                }

                await transaction.CommitAsync().ConfigureAwait(false);
            }
        }

        return new CheckpointInfo(sessionId, checkpointId);
    }

    /// <inheritdoc/>
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
    {
        _ = Throw.IfNull(key);
        ValidateSession(sessionId, key, nameof(key));
        FeatureUsageMarker.MarkUsed();
        var command = this._dataSource.CreateCommand($"""
            SELECT payload FROM {this._table}
            WHERE application_id = @application_id AND tenant_id = @tenant_id
                AND run_id = @run_id AND payload_format = @payload_format AND checkpoint_id = @checkpoint_id;
            """);
        await using (command.ConfigureAwait(false))
        {
            this.AddScopeParameters(command, sessionId);
            command.Parameters.AddWithValue("checkpoint_id", key.CheckpointId);
            var reader = await command.ExecuteReaderAsync().ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                if (!await reader.ReadAsync().ConfigureAwait(false))
                {
                    throw new InvalidOperationException("Checkpoint was not found in the configured application, tenant, and session.");
                }

                using var document = JsonDocument.Parse(reader.GetString(0));
                return document.RootElement.Clone();
            }
        }
    }

    /// <inheritdoc/>
    public override async ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(
        string sessionId,
        CheckpointInfo? withParent = null)
    {
        ValidateSession(sessionId, withParent, nameof(withParent));
        FeatureUsageMarker.MarkUsed();
        var parentFilter = withParent is null ? string.Empty : " AND parent_checkpoint_id = @parent_checkpoint_id";
        var command = this._dataSource.CreateCommand($"""
            SELECT checkpoint_id FROM {this._table}
            WHERE application_id = @application_id AND tenant_id = @tenant_id
                AND run_id = @run_id AND payload_format = @payload_format{parentFilter}
            ORDER BY sequence ASC;
            """);
        await using (command.ConfigureAwait(false))
        {
            this.AddScopeParameters(command, sessionId);
            if (withParent is not null)
            {
                command.Parameters.AddWithValue("parent_checkpoint_id", withParent.CheckpointId);
            }

            var reader = await command.ExecuteReaderAsync().ConfigureAwait(false);
            await using (reader.ConfigureAwait(false))
            {
                List<CheckpointInfo> checkpoints = [];
                while (await reader.ReadAsync().ConfigureAwait(false))
                {
                    checkpoints.Add(new CheckpointInfo(sessionId, reader.GetString(0)));
                }

                return checkpoints;
            }
        }
    }

    internal string CreateLockScope(string sessionId)
        => JsonSerializer.Serialize(
            new[] { this._table, this._applicationId, this._tenantId, sessionId, PayloadFormat },
            LockScopeJsonContext.Default.StringArray);

    private void AddScopeParameters(NpgsqlCommand command, string sessionId)
    {
        command.Parameters.AddWithValue("application_id", this._applicationId);
        command.Parameters.AddWithValue("tenant_id", this._tenantId);
        command.Parameters.AddWithValue("run_id", sessionId);
        command.Parameters.AddWithValue("payload_format", PayloadFormat);
    }

    private static void ValidateSession(string sessionId, CheckpointInfo? checkpoint, string parameterName)
    {
        _ = ValidateScope(sessionId, nameof(sessionId));
        if (checkpoint is not null && !string.Equals(sessionId, checkpoint.SessionId, StringComparison.Ordinal))
        {
            throw new ArgumentException("Checkpoint must belong to the requested session.", parameterName);
        }
    }

    private static string ValidateScope(string value, string parameterName)
    {
        _ = Throw.IfNullOrWhitespace(value, parameterName);
        if (value.Contains('\0'))
        {
            throw new ArgumentException("Scope identifiers cannot contain NUL.", parameterName);
        }

        return value;
    }

    private static string QuoteIdentifier(string value, string parameterName)
    {
        _ = Throw.IfNullOrWhitespace(value, parameterName);
        if (value.Contains('\0') || Encoding.UTF8.GetByteCount(value) > 63)
        {
            throw new ArgumentException("PostgreSQL identifiers must contain at most 63 UTF-8 bytes and no NUL.", parameterName);
        }

        using var builder = new NpgsqlCommandBuilder();
        return builder.QuoteIdentifier(value);
    }

    [JsonSerializable(typeof(string[]))]
    [ExcludeFromCodeCoverage]
    private sealed partial class LockScopeJsonContext : JsonSerializerContext;
}
