// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Npgsql;

namespace DevUIWithPostgresPersistence.AgentService;

internal sealed class PostgresAgentSessionStore : AgentSessionStore, IDisposable
{
    private readonly NpgsqlDataSource _dataSource;

    private PostgresAgentSessionStore(NpgsqlDataSource dataSource)
    {
        this._dataSource = dataSource;
    }

    public static async Task<PostgresAgentSessionStore> CreateAsync(
        string connectionString,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(connectionString);

        NpgsqlDataSource dataSource = NpgsqlDataSource.Create(connectionString);
        var store = new PostgresAgentSessionStore(dataSource);
        try
        {
            await store.InitializeAsync(cancellationToken).ConfigureAwait(false);
            return store;
        }
        catch
        {
            await dataSource.DisposeAsync().ConfigureAwait(false);
            throw;
        }
    }

    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        JsonElement serialized = await agent.SerializeSessionAsync(
            session,
            cancellationToken: cancellationToken).ConfigureAwait(false);
        await using NpgsqlCommand command = this._dataSource.CreateCommand(
            """
            INSERT INTO agent_sessions (agent_name, session_id, partitions, session)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (agent_name, session_id, partitions)
            DO UPDATE SET session = excluded.session
            """);
        command.Parameters.AddWithValue(GetAgentName(agent));
        command.Parameters.AddWithValue(key.SessionId);
        command.Parameters.AddWithValue(SerializePartitions(key.Partitions));
        command.Parameters.AddWithValue(serialized.GetRawText());
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }

    public override async ValueTask<AgentSession> GetOrCreateSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        AgentSession? session = await this.GetSessionAsync(agent, key, cancellationToken).ConfigureAwait(false);
        if (session is not null)
        {
            return session;
        }

        session = await agent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        session.StateBag.SetValue(
            DatabaseChatHistoryProvider.StateKey,
            new DatabaseChatHistoryProvider.State { HistoryId = CreateHistoryId(agent, key) });
        return session;
    }

    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        await using NpgsqlCommand command = this._dataSource.CreateCommand(
            """
            SELECT session
            FROM agent_sessions
            WHERE agent_name = $1 AND session_id = $2 AND partitions = $3
            """);
        command.Parameters.AddWithValue(GetAgentName(agent));
        command.Parameters.AddWithValue(key.SessionId);
        command.Parameters.AddWithValue(SerializePartitions(key.Partitions));
        object? value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
        if (value is not string json)
        {
            return null;
        }

        using JsonDocument document = JsonDocument.Parse(json);
        return await agent.DeserializeSessionAsync(
            document.RootElement,
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<IEnumerable<ChatMessage>> LoadChatHistoryAsync(
        string historyId,
        CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = this._dataSource.CreateCommand(
            """
            SELECT message::text
            FROM chat_messages
            WHERE history_id = $1
            ORDER BY position
            """);
        command.Parameters.AddWithValue(historyId);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        var messages = new List<ChatMessage>();
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            messages.Add(JsonSerializer.Deserialize<ChatMessage>(
                reader.GetString(0),
                AgentAbstractionsJsonUtilities.DefaultOptions)
                ?? throw new InvalidOperationException("Stored chat message could not be deserialized."));
        }

        return messages;
    }

    public async ValueTask ForkAndAppendChatHistoryAsync(
        string sourceHistoryId,
        string targetHistoryId,
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await this._dataSource.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync(cancellationToken).ConfigureAwait(false);
        await using (var forkCommand = new NpgsqlCommand(
            """
            INSERT INTO chat_messages (history_id, message)
            SELECT $2, message
            FROM chat_messages
            WHERE history_id = $1
            ORDER BY position
            """,
            connection,
            transaction))
        {
            forkCommand.Parameters.AddWithValue(sourceHistoryId);
            forkCommand.Parameters.AddWithValue(targetHistoryId);
            await forkCommand.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        foreach (ChatMessage message in messages)
        {
            await using var command = new NpgsqlCommand(
                "INSERT INTO chat_messages (history_id, message) VALUES ($1, $2)",
                connection,
                transaction);
            command.Parameters.AddWithValue(targetHistoryId);
            command.Parameters.AddWithValue(JsonSerializer.Serialize(
                message,
                AgentAbstractionsJsonUtilities.DefaultOptions));
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }

    public void Dispose()
    {
        this._dataSource.Dispose();
    }

    private static string GetAgentName(AIAgent agent)
        => agent.Name ?? throw new InvalidOperationException(
            "The sample requires a stable agent name for session persistence.");

    private static string CreateHistoryId(AIAgent agent, AgentSessionStoreKey key)
    {
        string scopedIdentity = string.Join(
            '\n',
            GetAgentName(agent),
            key.SessionId,
            SerializePartitions(key.Partitions));
        byte[] hash = System.Security.Cryptography.SHA256.HashData(
            System.Text.Encoding.UTF8.GetBytes(scopedIdentity));
        return $"{key.SessionId}:{Convert.ToHexString(hash)}";
    }

    private static string SerializePartitions(IReadOnlyDictionary<string, string>? partitions)
    {
        var sorted = new SortedDictionary<string, string>(StringComparer.Ordinal);
        if (partitions is not null)
        {
            foreach (KeyValuePair<string, string> partition in partitions)
            {
                sorted.Add(partition.Key, partition.Value);
            }
        }

        return JsonSerializer.Serialize(sorted, AgentAbstractionsJsonUtilities.DefaultOptions);
    }

    private async Task InitializeAsync(CancellationToken cancellationToken)
    {
        await using NpgsqlCommand command = this._dataSource.CreateCommand(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                agent_name TEXT NOT NULL,
                session_id TEXT NOT NULL,
                partitions TEXT NOT NULL,
                session TEXT NOT NULL,
                PRIMARY KEY (agent_name, session_id, partitions)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                position BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                history_id TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS ix_chat_messages_history
                ON chat_messages (history_id, position);
            """);
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }
}
