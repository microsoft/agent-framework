// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Data.Sqlite;

namespace AspNetAgentPersistence;

internal sealed class ConversationStore
{
    private readonly string _connectionString;

    public ConversationStore(string databasePath)
    {
        this._connectionString = new SqliteConnectionStringBuilder { DataSource = databasePath, Pooling = false }.ToString();
        using var connection = new SqliteConnection(this._connectionString);
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "CREATE TABLE IF NOT EXISTS Conversations (Id TEXT PRIMARY KEY, Session TEXT NOT NULL)";
        command.ExecuteNonQuery();
    }

    public async Task<AgentSession> LoadAsync(AIAgent agent, Guid conversationId, CancellationToken cancellationToken = default)
    {
        using var connection = new SqliteConnection(this._connectionString);
        await connection.OpenAsync(cancellationToken);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Session FROM Conversations WHERE Id = $id";
        command.Parameters.AddWithValue("$id", conversationId.ToString("N"));
        if (await command.ExecuteScalarAsync(cancellationToken) is string json)
        {
            using JsonDocument document = JsonDocument.Parse(json);
            return await agent.DeserializeSessionAsync(document.RootElement, cancellationToken: cancellationToken);
        }

        return await agent.CreateSessionAsync(cancellationToken);
    }

    public async Task SaveAsync(AIAgent agent, Guid conversationId, AgentSession session, CancellationToken cancellationToken = default)
    {
        JsonElement serialized = await agent.SerializeSessionAsync(session, cancellationToken: cancellationToken);
        using var connection = new SqliteConnection(this._connectionString);
        await connection.OpenAsync(cancellationToken);
        using var command = connection.CreateCommand();
        command.CommandText = "INSERT INTO Conversations (Id, Session) VALUES ($id, $session) ON CONFLICT(Id) DO UPDATE SET Session = excluded.Session";
        command.Parameters.AddWithValue("$id", conversationId.ToString("N"));
        command.Parameters.AddWithValue("$session", serialized.GetRawText());
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}
