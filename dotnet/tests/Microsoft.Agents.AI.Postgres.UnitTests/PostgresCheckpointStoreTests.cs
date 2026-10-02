// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Tests checkpoint scope validation before database access.
/// </summary>
public sealed class PostgresCheckpointStoreTests
{
    [Theory]
    [InlineData("app", "tenant", "run")]
    [InlineData("app\"\\,[]", "tenant|:<>\u00e9\u4e2d", "run\ud83d\ude80")]
    [InlineData("app\b\f", "tenant\n\r\t", "run\u0001\u000b\u001f")]
    public async Task LockScope_PreservesEveryComponentAsync(string applicationId, string tenantId, string sessionId)
    {
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        var store = new PostgresCheckpointStore(dataSource, applicationId, tenantId);

        using var scope = JsonDocument.Parse(store.CreateLockScope(sessionId));

        Assert.Equal(
            ["\"public\".\"agent_framework_checkpoints\"", applicationId, tenantId, sessionId, "agent-framework.dotnet.checkpoint.v1"],
            scope.RootElement.EnumerateArray().Select(component => component.GetString()));
    }

    [Fact]
    public void Constructor_RejectsNullDataSource()
    {
        Assert.Throws<ArgumentNullException>(() => new PostgresCheckpointStore(null!, "app", "tenant"));
    }

    [Theory]
    [InlineData("", "tenant")]
    [InlineData("app", " ")]
    [InlineData("app\0", "tenant")]
    [InlineData("app", "tenant\0")]
    public async Task Constructor_RejectsInvalidScopeAsync(string applicationId, string tenantId)
    {
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        Assert.Throws<ArgumentException>(() => new PostgresCheckpointStore(dataSource, applicationId, tenantId));
    }

    [Theory]
    [InlineData("")]
    [InlineData("bad\0name")]
    [InlineData("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijkl")]
    public async Task Constructor_RejectsInvalidTableNameAsync(string tableName)
    {
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        Assert.Throws<ArgumentException>(() => new PostgresCheckpointStore(dataSource, "app", "tenant", tableName: tableName));
    }

    [Fact]
    public async Task Operations_RejectCrossSessionKeysAsync()
    {
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        var store = new PostgresCheckpointStore(dataSource, "app", "tenant");
        var foreignKey = new CheckpointInfo("other-session", "checkpoint");
        using var document = JsonDocument.Parse("{}");

        await Assert.ThrowsAsync<ArgumentException>(() => store.CreateCheckpointAsync("session", document.RootElement, foreignKey).AsTask());
        await Assert.ThrowsAsync<ArgumentException>(() => store.RetrieveCheckpointAsync("session", foreignKey).AsTask());
        await Assert.ThrowsAsync<ArgumentException>(() => store.RetrieveIndexAsync("session", foreignKey).AsTask());
    }

    [Fact]
    public async Task Operations_RejectInvalidArgumentsAsync()
    {
        await using var dataSource = new NpgsqlDataSourceBuilder("Host=localhost").Build();
        var store = new PostgresCheckpointStore(dataSource, "app", "tenant");

        await Assert.ThrowsAsync<ArgumentException>(() => store.CreateCheckpointAsync("session", default).AsTask());
        await Assert.ThrowsAsync<ArgumentException>(() => store.RetrieveIndexAsync(" ").AsTask());
        await Assert.ThrowsAsync<ArgumentNullException>(() => store.RetrieveCheckpointAsync("session", null!).AsTask());
    }
}
