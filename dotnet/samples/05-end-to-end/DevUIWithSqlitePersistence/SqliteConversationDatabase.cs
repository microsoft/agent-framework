// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.AI;

namespace DevUIWithSqlitePersistence;

internal sealed class SqliteConversationDatabase : AgentSessionStore, IOpenAIConversationStore
{
    private readonly string _connectionString;

    public SqliteConversationDatabase(string databasePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(databasePath);
        this._connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
            ForeignKeys = true,
            Pooling = false,
        }.ToString();
        this.Initialize();
    }

    public override async ValueTask SaveSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        AgentSession session,
        CancellationToken cancellationToken = default)
    {
        JsonElement serialized = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken).ConfigureAwait(false);
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            """
            INSERT INTO AgentSessions (AgentName, SessionId, Partitions, Session)
            VALUES ($agentName, $sessionId, $partitions, $session)
            ON CONFLICT(AgentName, SessionId, Partitions)
            DO UPDATE SET Session = excluded.Session
            """;
        command.Parameters.AddWithValue("$agentName", GetAgentName(agent));
        command.Parameters.AddWithValue("$sessionId", key.SessionId);
        command.Parameters.AddWithValue("$partitions", SerializePartitions(key.Partitions));
        command.Parameters.AddWithValue("$session", serialized.GetRawText());
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }

    public override async ValueTask<AgentSession?> GetSessionAsync(
        AIAgent agent,
        AgentSessionStoreKey key,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            """
            SELECT Session
            FROM AgentSessions
            WHERE AgentName = $agentName AND SessionId = $sessionId AND Partitions = $partitions
            """;
        command.Parameters.AddWithValue("$agentName", GetAgentName(agent));
        command.Parameters.AddWithValue("$sessionId", key.SessionId);
        command.Parameters.AddWithValue("$partitions", SerializePartitions(key.Partitions));
        object? value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
        if (value is not string json)
        {
            return null;
        }

        using JsonDocument document = JsonDocument.Parse(json);
        return await agent.DeserializeSessionAsync(document.RootElement, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask CreateConversationAsync(
        OpenAIConversationRecord conversation,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText = "INSERT INTO Conversations (Id, Data) VALUES ($id, $data)";
        command.Parameters.AddWithValue("$id", conversation.Id);
        command.Parameters.AddWithValue("$data", conversation.Data.GetRawText());
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<OpenAIConversationRecord?> GetConversationAsync(
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText = "SELECT Data FROM Conversations WHERE Id = $id";
        command.Parameters.AddWithValue("$id", conversationId);
        object? value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
        return value is string json ? new OpenAIConversationRecord { Id = conversationId, Data = ParseJson(json) } : null;
    }

    public async ValueTask<bool> UpdateConversationAsync(
        OpenAIConversationRecord conversation,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText = "UPDATE Conversations SET Data = $data WHERE Id = $id";
        command.Parameters.AddWithValue("$id", conversation.Id);
        command.Parameters.AddWithValue("$data", conversation.Data.GetRawText());
        return await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false) > 0;
    }

    public async ValueTask<bool> DeleteConversationAsync(
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText = "DELETE FROM Conversations WHERE Id = $id";
        command.Parameters.AddWithValue("$id", conversationId);
        return await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false) > 0;
    }

    public async ValueTask AddItemsAsync(
        string conversationId,
        IReadOnlyList<OpenAIConversationItem> items,
        CancellationToken cancellationToken = default)
    {
        if (items.Count == 0)
        {
            return;
        }

        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        using SqliteTransaction transaction = connection.BeginTransaction();
        foreach (OpenAIConversationItem item in items)
        {
            await using SqliteCommand command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText =
                "INSERT INTO ConversationItems (ConversationId, ItemId, Data) VALUES ($conversationId, $itemId, $data)";
            command.Parameters.AddWithValue("$conversationId", conversationId);
            command.Parameters.AddWithValue("$itemId", item.Id);
            command.Parameters.AddWithValue("$data", item.Data.GetRawText());
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<OpenAIConversationItem?> GetItemAsync(
        string conversationId,
        string itemId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            "SELECT Data FROM ConversationItems WHERE ConversationId = $conversationId AND ItemId = $itemId";
        command.Parameters.AddWithValue("$conversationId", conversationId);
        command.Parameters.AddWithValue("$itemId", itemId);
        object? value = await command.ExecuteScalarAsync(cancellationToken).ConfigureAwait(false);
        return value is string json ? new OpenAIConversationItem { Id = itemId, Data = ParseJson(json) } : null;
    }

    public async ValueTask<OpenAIConversationItemsPage> ListItemsAsync(
        string conversationId,
        int limit,
        OpenAIConversationItemOrder order,
        string? after,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            $"""
            SELECT ItemId, Data
            FROM ConversationItems
            WHERE ConversationId = $conversationId
            ORDER BY Position {(order is OpenAIConversationItemOrder.Ascending ? "ASC" : "DESC")}
            """;
        command.Parameters.AddWithValue("$conversationId", conversationId);
        await using SqliteDataReader reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        var allItems = new List<OpenAIConversationItem>();
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            allItems.Add(new OpenAIConversationItem
            {
                Id = reader.GetString(0),
                Data = ParseJson(reader.GetString(1)),
            });
        }

        IEnumerable<OpenAIConversationItem> filtered = allItems;
        if (after is not null)
        {
            int afterIndex = allItems.FindIndex(item => item.Id == after);
            if (afterIndex >= 0)
            {
                filtered = allItems.Skip(afterIndex + 1);
            }
        }

        List<OpenAIConversationItem> page = [.. filtered.Take(limit + 1)];
        bool hasMore = page.Count > limit;
        if (hasMore)
        {
            page.RemoveAt(page.Count - 1);
        }

        return new OpenAIConversationItemsPage { Items = page, HasMore = hasMore };
    }

    public async ValueTask<bool> DeleteItemAsync(
        string conversationId,
        string itemId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            "DELETE FROM ConversationItems WHERE ConversationId = $conversationId AND ItemId = $itemId";
        command.Parameters.AddWithValue("$conversationId", conversationId);
        command.Parameters.AddWithValue("$itemId", itemId);
        return await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false) > 0;
    }

    public async ValueTask AddConversationToAgentAsync(
        string agentId,
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            """
            INSERT INTO AgentConversations (AgentId, ConversationId)
            VALUES ($agentId, $conversationId)
            ON CONFLICT(AgentId, ConversationId) DO NOTHING
            """;
        command.Parameters.AddWithValue("$agentId", agentId);
        command.Parameters.AddWithValue("$conversationId", conversationId);
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask RemoveConversationFromAgentAsync(
        string agentId,
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            "DELETE FROM AgentConversations WHERE AgentId = $agentId AND ConversationId = $conversationId";
        command.Parameters.AddWithValue("$agentId", agentId);
        command.Parameters.AddWithValue("$conversationId", conversationId);
        await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask<IReadOnlyList<string>> ListConversationIdsAsync(
        string agentId,
        CancellationToken cancellationToken = default)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            "SELECT ConversationId FROM AgentConversations WHERE AgentId = $agentId ORDER BY ConversationId";
        command.Parameters.AddWithValue("$agentId", agentId);
        await using SqliteDataReader reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
        var conversationIds = new List<string>();
        while (await reader.ReadAsync(cancellationToken).ConfigureAwait(false))
        {
            conversationIds.Add(reader.GetString(0));
        }

        return conversationIds;
    }

    internal async ValueTask<IEnumerable<ChatMessage>> LoadChatHistoryAsync(
        string historyId,
        CancellationToken cancellationToken)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        await using SqliteCommand command = connection.CreateCommand();
        command.CommandText = "SELECT Data FROM ChatMessages WHERE HistoryId = $historyId ORDER BY Position";
        command.Parameters.AddWithValue("$historyId", historyId);
        await using SqliteDataReader reader = await command.ExecuteReaderAsync(cancellationToken).ConfigureAwait(false);
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

    internal async ValueTask AppendChatHistoryAsync(
        string historyId,
        IEnumerable<ChatMessage> messages,
        CancellationToken cancellationToken)
    {
        await using SqliteConnection connection = await this.OpenConnectionAsync(cancellationToken).ConfigureAwait(false);
        using SqliteTransaction transaction = connection.BeginTransaction();
        foreach (ChatMessage message in messages)
        {
            await using SqliteCommand command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = "INSERT INTO ChatMessages (HistoryId, Data) VALUES ($historyId, $data)";
            command.Parameters.AddWithValue("$historyId", historyId);
            command.Parameters.AddWithValue(
                "$data",
                JsonSerializer.Serialize(message, AgentAbstractionsJsonUtilities.DefaultOptions));
            await command.ExecuteNonQueryAsync(cancellationToken).ConfigureAwait(false);
        }

        await transaction.CommitAsync(cancellationToken).ConfigureAwait(false);
    }

    private static string GetAgentName(AIAgent agent)
        => agent.Name ?? throw new InvalidOperationException("The sample requires a stable agent name for session persistence.");

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

    private static JsonElement ParseJson(string json)
    {
        using JsonDocument document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    private async ValueTask<SqliteConnection> OpenConnectionAsync(CancellationToken cancellationToken)
    {
        var connection = new SqliteConnection(this._connectionString);
        await connection.OpenAsync(cancellationToken).ConfigureAwait(false);
        return connection;
    }

    private void Initialize()
    {
        using var connection = new SqliteConnection(this._connectionString);
        connection.Open();
        using SqliteCommand command = connection.CreateCommand();
        command.CommandText =
            """
            CREATE TABLE IF NOT EXISTS AgentSessions (
                AgentName TEXT NOT NULL,
                SessionId TEXT NOT NULL,
                Partitions TEXT NOT NULL,
                Session TEXT NOT NULL,
                PRIMARY KEY (AgentName, SessionId, Partitions)
            );

            CREATE TABLE IF NOT EXISTS Conversations (
                Id TEXT PRIMARY KEY,
                Data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ConversationItems (
                Position INTEGER PRIMARY KEY AUTOINCREMENT,
                ConversationId TEXT NOT NULL,
                ItemId TEXT NOT NULL,
                Data TEXT NOT NULL,
                UNIQUE (ConversationId, ItemId),
                FOREIGN KEY (ConversationId) REFERENCES Conversations(Id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS AgentConversations (
                AgentId TEXT NOT NULL,
                ConversationId TEXT NOT NULL,
                PRIMARY KEY (AgentId, ConversationId),
                FOREIGN KEY (ConversationId) REFERENCES Conversations(Id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ChatMessages (
                Position INTEGER PRIMARY KEY AUTOINCREMENT,
                HistoryId TEXT NOT NULL,
                Data TEXT NOT NULL
            );
            """;
        command.ExecuteNonQuery();
    }
}
