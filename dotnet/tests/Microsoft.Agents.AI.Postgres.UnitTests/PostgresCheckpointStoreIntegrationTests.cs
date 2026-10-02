// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;
using Npgsql;
using NpgsqlTypes;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Exercises checkpoints against an explicitly designated PostgreSQL database without pgvector.
/// </summary>
[Trait("Category", "Postgres")]
public sealed class PostgresCheckpointStoreIntegrationTests : IAsyncLifetime
{
    private readonly string _schema = $"af_checkpoint_{Guid.NewGuid():N}";
    private NpgsqlDataSource? _dataSource;
    private string? _connectionString;

    public async ValueTask InitializeAsync()
    {
        this._connectionString = Environment.GetEnvironmentVariable("POSTGRES_CHECKPOINT_CONNECTION_STRING");
        if (string.IsNullOrWhiteSpace(this._connectionString))
        {
            return;
        }

        this._dataSource = NpgsqlDataSource.Create(this._connectionString);
        await using var command = this._dataSource.CreateCommand($"CREATE SCHEMA \"{this._schema}\";");
        await command.ExecuteNonQueryAsync();
    }

    public async ValueTask DisposeAsync()
    {
        if (this._dataSource is not null)
        {
            await using var command = this._dataSource.CreateCommand($"DROP SCHEMA IF EXISTS \"{this._schema}\" CASCADE;");
            await command.ExecuteNonQueryAsync();
            await this._dataSource.DisposeAsync();
        }
    }

    [Fact]
    public async Task Store_RoundTripsAcrossDataSourcesWithParentAndHistoryAsync()
    {
        var dataSource = this.GetDataSourceOrSkip();
        var store = new PostgresCheckpointStore(dataSource, "app", "tenant", this._schema, "checkpoints\"; --");
        await store.EnsureTableAsync();
        using var document = JsonDocument.Parse("""{"state":{"visits":[1]},"pending":["approval"]}""");
        var first = await store.CreateCheckpointAsync("run", document.RootElement);
        var second = await store.CreateCheckpointAsync("run", document.RootElement, first);

        await using var reopenedDataSource = NpgsqlDataSource.Create(this._connectionString!);
        var reopened = new PostgresCheckpointStore(reopenedDataSource, "app", "tenant", this._schema, "checkpoints\"; --");
        await reopened.EnsureTableAsync();
        var loaded = await reopened.RetrieveCheckpointAsync("run", first);
        Assert.Equal(1, loaded.GetProperty("state").GetProperty("visits")[0].GetInt32());
        Assert.Equal("approval", loaded.GetProperty("pending")[0].GetString());
        Assert.Equal([first, second], await reopened.RetrieveIndexAsync("run"));
        Assert.Equal([second], await reopened.RetrieveIndexAsync("run", first));
        Assert.Equal(second, await reopened.CreateCheckpointManager().GetLatestCheckpointAsync("run"));
        Assert.Null(await reopened.CreateCheckpointManager().GetLatestCheckpointAsync("missing"));
    }

    [Theory]
    [InlineData("other-app", "tenant", "run")]
    [InlineData("app", "other-tenant", "run")]
    [InlineData("app", "tenant", "other-run")]
    public async Task Store_IsolatesApplicationTenantAndRunAsync(string applicationId, string tenantId, string runId)
    {
        var dataSource = this.GetDataSourceOrSkip();
        var store = new PostgresCheckpointStore(dataSource, "app", "tenant", this._schema);
        await store.EnsureTableAsync();
        using var document = JsonDocument.Parse("{}");
        var checkpoint = await store.CreateCheckpointAsync("run", document.RootElement);

        var other = new PostgresCheckpointStore(dataSource, applicationId, tenantId, this._schema);
        Assert.Empty(await other.RetrieveIndexAsync(runId));
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => other.RetrieveCheckpointAsync(runId, new CheckpointInfo(runId, checkpoint.CheckpointId)).AsTask());
        var otherCheckpoint = await other.CreateCheckpointAsync(runId, document.RootElement);
        Assert.Equal([checkpoint], await store.RetrieveIndexAsync("run"));
        Assert.Equal([otherCheckpoint], await other.RetrieveIndexAsync(runId));
    }

    [Fact]
    public async Task Store_IgnoresPythonPayloadsInTheSameTableAsync()
    {
        var dataSource = this.GetDataSourceOrSkip();
        var store = new PostgresCheckpointStore(dataSource, "app", "tenant", this._schema);
        await store.EnsureTableAsync();
        using var document = JsonDocument.Parse("""{"runtime":"dotnet"}""");
        var checkpoint = await store.CreateCheckpointAsync("run", document.RootElement);
        await using var insert = dataSource.CreateCommand($"""
            INSERT INTO "{this._schema}".agent_framework_checkpoints
                (application_id, tenant_id, run_id, payload_format, checkpoint_id, workflow_name, payload)
            VALUES ('app', 'tenant', 'run', 'agent-framework.python.checkpoint.v1', @checkpoint_id, 'approval', @payload),
                   ('app', 'tenant', 'run', 'agent-framework.python.checkpoint.v1', 'python-only', 'approval', @payload);
            """);
        insert.Parameters.AddWithValue("checkpoint_id", checkpoint.CheckpointId);
        insert.Parameters.AddWithValue("payload", NpgsqlDbType.Jsonb, """{"runtime":"python"}""");
        await insert.ExecuteNonQueryAsync();

        Assert.Equal([checkpoint], await store.RetrieveIndexAsync("run"));
        Assert.Equal(checkpoint, await store.CreateCheckpointManager().GetLatestCheckpointAsync("run"));
        Assert.Equal("dotnet", (await store.RetrieveCheckpointAsync("run", checkpoint)).GetProperty("runtime").GetString());
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => store.RetrieveCheckpointAsync("run", new CheckpointInfo("run", "python-only")).AsTask());
    }

    [Fact]
    public async Task Store_ConcurrentWritersPreserveAllCheckpointsAsync()
    {
        var store = new PostgresCheckpointStore(this.GetDataSourceOrSkip(), "app", "tenant", this._schema);
        await store.EnsureTableAsync();
        using var document = JsonDocument.Parse("{}");
        var saved = await Task.WhenAll(Enumerable.Range(0, 12).Select(_ => store.CreateCheckpointAsync("run", document.RootElement).AsTask()));
        var listed = (await store.RetrieveIndexAsync("run")).ToList();
        Assert.Equal(12, listed.Count);
        Assert.Equal(saved.OrderBy(checkpoint => checkpoint.CheckpointId), listed.OrderBy(checkpoint => checkpoint.CheckpointId));
        Assert.Equal(listed[^1], await store.CreateCheckpointManager().GetLatestCheckpointAsync("run"));
    }

    [Fact]
    public async Task Workflow_ResumesApprovalAfterJsonbReordersMetadataAsync()
    {
        var store = new PostgresCheckpointStore(this.GetDataSourceOrSkip(), "app", "tenant", this._schema);
        await store.EnsureTableAsync();
        CheckpointInfo? saved = null;
        var requested = false;
        await using (var run = await InProcessExecution.RunStreamingAsync(CreateApprovalWorkflow(), "PO-1042", store.CreateCheckpointManager(), sessionId: "workflow"))
        {
            await foreach (var workflowEvent in run.WatchStreamAsync())
            {
                if (workflowEvent is RequestInfoEvent)
                {
                    requested = true;
                }

                if (requested && workflowEvent is SuperStepCompletedEvent step && step.CompletionInfo?.Checkpoint is { } checkpoint)
                {
                    saved = checkpoint;
                    break;
                }
            }
        }

        Assert.NotNull(saved);
        await using var reopenedDataSource = NpgsqlDataSource.Create(this._connectionString!);
        var reopened = new PostgresCheckpointStore(reopenedDataSource, "app", "tenant", this._schema);
        await using var resumed = await InProcessExecution.ResumeStreamingAsync(CreateApprovalWorkflow(), saved, reopened.CreateCheckpointManager());
        var answered = false;
        string? result = null;
        await foreach (var workflowEvent in resumed.WatchStreamAsync())
        {
            if (workflowEvent is RequestInfoEvent requestEvent)
            {
                await resumed.SendResponseAsync(requestEvent.Request.CreateResponse(true));
                answered = true;
            }
            else if (workflowEvent is WorkflowOutputEvent output)
            {
                result = Assert.IsType<string>(output.Data);
            }
        }

        Assert.True(answered);
        Assert.Equal("approved", result);
    }

    private static Workflow CreateApprovalWorkflow()
    {
        var approval = RequestPort.Create<string, bool>("approval");
        var decision = new DecisionExecutor();
        return new WorkflowBuilder(approval).AddEdge(approval, decision).WithOutputFrom(decision).Build();
    }

    private sealed class DecisionExecutor() : Executor<bool, string>("decision")
    {
        public override ValueTask<string> HandleAsync(bool message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => ValueTask.FromResult(message ? "approved" : "rejected");
    }

    private NpgsqlDataSource GetDataSourceOrSkip()
    {
        Assert.SkipWhen(this._dataSource is null, "Set POSTGRES_CHECKPOINT_CONNECTION_STRING to a designated test database.");
        return this._dataSource;
    }
}
