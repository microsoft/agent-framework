// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Exercises Azure AI reranking and hybrid fallback against an explicitly designated test database.
/// </summary>
/// <remarks>
/// Set POSTGRES_AZURE_AI_CONNECTION_STRING to opt in. Success and failure scenarios also require
/// POSTGRES_AZURE_AI_RERANKER_MODEL and POSTGRES_AZURE_AI_FAILURE_MODEL, respectively.
/// </remarks>
[Trait("Category", "Postgres")]
[Trait("Dependency", "AzureAI")]
public sealed class AzureRankLiveIntegrationTests : IAsyncLifetime
{
    private readonly string _schema = $"af_azure_rank_{Guid.NewGuid():N}";
    private readonly PostgresMemoryScope _scope = new() { UserId = "synthetic-user", ThreadId = "synthetic-thread" };
    private readonly Mock<IEmbeddingGenerator<string, Embedding<float>>> _embeddings = new();
    private readonly Mock<IChatClient> _chat = new(MockBehavior.Strict);
    private readonly Mock<ILogger> _logger = new();
    private readonly Mock<ILoggerFactory> _loggerFactory = new();
    private NpgsqlDataSource? _dataSource;

    public ValueTask InitializeAsync()
    {
        var connectionString = Environment.GetEnvironmentVariable("POSTGRES_AZURE_AI_CONNECTION_STRING");
        if (!string.IsNullOrWhiteSpace(connectionString))
        {
            var builder = new NpgsqlDataSourceBuilder(connectionString);
            builder.UseVector();
            this._dataSource = builder.Build();
        }

        this._embeddings.Setup(generator => generator.GenerateAsync(
            It.IsAny<IEnumerable<string>>(),
            It.IsAny<EmbeddingGenerationOptions>(),
            It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<string> values, EmbeddingGenerationOptions? _, CancellationToken _) =>
                new GeneratedEmbeddings<Embedding<float>>(
                    values.Select(_ => new Embedding<float>(new float[] { 1, 0, 0 }))));
        this._logger.Setup(logger => logger.IsEnabled(LogLevel.Warning)).Returns(true);
        this._loggerFactory.Setup(factory => factory.CreateLogger(It.IsAny<string>())).Returns(this._logger.Object);
        return ValueTask.CompletedTask;
    }

    public async ValueTask DisposeAsync()
    {
        if (this._dataSource is not null)
        {
            try
            {
                await using var cleanup = this._dataSource.CreateCommand($"DROP SCHEMA IF EXISTS \"{this._schema}\" CASCADE;");
                await cleanup.ExecuteNonQueryAsync();
            }
            finally
            {
                await this._dataSource.DisposeAsync();
            }
        }
    }

    [Fact]
    public async Task SearchAsync_RerankingDisabledReturnsHybridResultsAsync()
    {
        // Arrange
        await this.SeedAsync();
        await using var client = this.CreateClient();

        // Act
        var results = await client.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 2);

        // Assert
        Assert.Equal(2, results.Count);
        Assert.All(results, record =>
        {
            Assert.NotNull(record.Score);
            Assert.Null(record.RerankerScore);
        });
        this.VerifyWarnings(Times.Never());
        this._chat.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task SearchAsync_SingleCandidateSkipsRerankingAsync()
    {
        // Arrange
        await this.SeedAsync(count: 1);
        await using var client = this.CreateClient("unused-single-candidate-model");

        // Act
        var results = await client.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 2);

        // Assert
        Assert.Null(Assert.Single(results).RerankerScore);
        this.VerifyWarnings(Times.Never());
        this._chat.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task SearchAsync_ConfiguredRerankerReturnsSemanticScoresAsync()
    {
        // Arrange
        var model = GetModelOrSkip("POSTGRES_AZURE_AI_RERANKER_MODEL");
        await this.SeedAsync();
        await using var baseline = this.CreateClient();
        var candidates = await baseline.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 3);
        Assert.Equal(3, candidates.Count);
        var candidatesById = candidates.ToDictionary(record => record.Id);
        await using var client = this.CreateClient(model);

        // Act
        var results = await client.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 2);

        // Assert
        Assert.Equal(2, results.Count);
        Assert.Equal(2, results.Select(record => record.Id).Distinct().Count());
        Assert.All(results, record =>
        {
            Assert.True(candidatesById.ContainsKey(record.Id));
            Assert.Equal(candidatesById[record.Id].Score, record.Score);
            Assert.NotNull(record.RerankerScore);
            Assert.True(double.IsFinite(record.RerankerScore.Value));
        });
        this.VerifyWarnings(Times.Never());
        this._chat.VerifyNoOtherCalls();
    }

    [Fact]
    public async Task SearchAsync_UnavailableRerankerReturnsHybridResultsAndConnectionRemainsUsableAsync()
    {
        // Arrange
        var model = GetModelOrSkip("POSTGRES_AZURE_AI_FAILURE_MODEL");
        await this.SeedAsync();
        await using var baseline = this.CreateClient();
        var expected = await baseline.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 2);
        Assert.Equal(2, expected.Count);
        await using var client = this.CreateClient(model);

        // Act
        var results = await client.SearchAsync(this._scope.ToUserScope(), "PostgreSQL", topK: 2);

        // Assert
        Assert.Equal(expected.Select(record => record.Id), results.Select(record => record.Id));
        Assert.Equal(expected.Select(record => record.Score), results.Select(record => record.Score));
        Assert.All(results, record => Assert.Null(record.RerankerScore));
        this.VerifyWarnings(Times.Once());
        _ = await client.UpsertMemoryAsync(this._scope, "user", "Synthetic turn after rank failure.");
        Assert.Equal("Synthetic turn after rank failure.", Assert.Single(await client.GetThreadAsync(this._scope)).Content);
        Assert.Empty(await client.SearchAsync(
            new PostgresMemoryScope { UserId = "different-user" }, "PostgreSQL", topK: 2));
        this._chat.VerifyNoOtherCalls();
    }

    private static string GetModelOrSkip(string variable)
    {
        var model = Environment.GetEnvironmentVariable(variable);
        Assert.SkipWhen(string.IsNullOrWhiteSpace(model), $"Set {variable} to run this Azure AI scenario.");
        return model;
    }

    private NpgsqlDataSource GetDataSourceOrSkip()
    {
        Assert.SkipWhen(
            this._dataSource is null,
            "Set POSTGRES_AZURE_AI_CONNECTION_STRING to run Azure AI integration tests.");
        return this._dataSource;
    }

    private PostgresMemoryClientOptions CreateOptions(string? model = null) =>
        new()
        {
            Schema = this._schema,
            TableName = "memory",
            EmbeddingDimensions = 3,
            AutoProcess = false,
            EnableAzureAiReranking = model is not null,
            AzureAiRerankerModel = model ?? "cohere-rerank-v3.5",
            RerankingCandidateCount = 3,
        };

    private PostgresMemoryClient CreateClient(string? model = null) =>
        new(this.GetDataSourceOrSkip(), this._embeddings.Object, this._chat.Object, this.CreateOptions(model), this._loggerFactory.Object);

    private async Task SeedAsync(int count = 3)
    {
        var dataSource = this.GetDataSourceOrSkip();
        await using var extensions = dataSource.CreateCommand(
            "SELECT count(*) FROM pg_extension WHERE extname IN ('vector', 'azure_ai');");
        Assert.Equal(
            2L,
            await extensions.ExecuteScalarAsync());
        var store = new PostgresMemoryStore(dataSource, this.CreateOptions());
        await store.EnsureSchemaAsync(CancellationToken.None);
        for (var index = 0; index < count; index++)
        {
            _ = await store.InsertDerivedMemoryAsync(
                this._scope,
                PostgresMemoryType.Fact,
                $"Synthetic PostgreSQL preference {index}.",
                0.95,
                null,
                [],
                new float[] { 1, index * 0.1f, 0 },
                null,
                CancellationToken.None);
        }
    }

    private void VerifyWarnings(Times times) =>
        this._logger.Verify(logger => logger.Log(
            LogLevel.Warning,
            It.IsAny<EventId>(),
            It.Is<It.IsAnyType>((state, _) =>
                state.ToString() == "Azure AI memory reranking failed; returning hybrid retrieval order."),
            It.Is<Exception>(exception => exception is NpgsqlException),
            It.IsAny<Func<It.IsAnyType, Exception?, string>>()), times);
}
