// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Npgsql;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Tests for <see cref="PostgresMemoryClient"/>.
/// </summary>
public sealed class PostgresMemoryClientTests
{
    private static readonly ReadOnlyMemory<float> s_embedding = new([0.1f, 0.2f, 0.3f]);

    private readonly Mock<IPostgresMemoryStore> _store = new();
    private readonly Mock<IEmbeddingGenerator<string, Embedding<float>>> _embeddingGenerator = new();
    private readonly Mock<IChatClient> _chatClient = new();

    public PostgresMemoryClientTests()
    {
        this._embeddingGenerator
            .Setup(generator => generator.GenerateAsync(
                It.IsAny<IEnumerable<string>>(),
                It.IsAny<EmbeddingGenerationOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<string> values, EmbeddingGenerationOptions? _, CancellationToken _) =>
                new GeneratedEmbeddings<Embedding<float>>(
                    values.Select(_ => new Embedding<float>(s_embedding))));
        this._store
            .Setup(store => store.GetProcessingStateAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(default(ProcessingState));
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        this._store
            .Setup(store => store.GetRecentThreadSummariesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<int>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        this._store
            .Setup(store => store.GetLatestSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<PostgresMemoryType>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((null, 0L));
    }

    [Fact]
    public async Task UpsertMemoryAsync_NormalizesAssistantRoleAsync()
    {
        this._store
            .Setup(store => store.InsertTurnAsync(
                It.IsAny<PostgresMemoryScope>(),
                "agent",
                "hello",
                null,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(42);
        var client = this.CreateClient(new PostgresMemoryClientOptions { AutoProcess = false });

        var id = await client.UpsertMemoryAsync(CreateScope(), "assistant", " hello ");

        Assert.Equal(42, id);
        this._store.Verify(store => store.EnsureSchemaAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task SearchAsync_EmbedsQueryAndPassesRetrievalFiltersAsync()
    {
        this._store
            .Setup(store => store.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                "postgres preferences",
                s_embedding,
                It.Is<IReadOnlyList<PostgresMemoryType>>(types =>
                    types.SequenceEqual(new[] { PostgresMemoryType.Fact })),
                7,
                0.8,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        var client = this.CreateClient();

        _ = await client.SearchAsync(
            CreateScope(),
            "postgres preferences",
            [PostgresMemoryType.Fact],
            7,
            0.8);

        this._embeddingGenerator.Verify(
            generator => generator.GenerateAsync(
                It.Is<IEnumerable<string>>(values => values.Single() == "postgres preferences"),
                It.IsAny<EmbeddingGenerationOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task SearchAsync_ReranksExpandedCandidatePoolAsync()
    {
        // Arrange
        var first = CreateRecord(1, PostgresMemoryType.Fact, "PostgreSQL tuning guidance.");
        var second = CreateRecord(2, PostgresMemoryType.Fact, "The user prefers PostgreSQL.");
        var third = CreateRecord(3, PostgresMemoryType.Fact, "A MySQL migration occurred.");
        this._store
            .Setup(store => store.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                "preferred database",
                s_embedding,
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                25,
                0.7,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([first, second, third]);
        this._store
            .Setup(store => store.RerankAsync(
                "preferred database",
                It.IsAny<IReadOnlyList<PostgresMemoryRecord>>(),
                "cohere-rerank-v3.5",
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                new PostgresMemoryRerankResult(2, 1, 0.98),
                new PostgresMemoryRerankResult(1, 2, 0.63),
                new PostgresMemoryRerankResult(3, 3, 0.12),
            ]);
        var client = this.CreateClient(new PostgresMemoryClientOptions
        {
            AutoProcess = false,
            EnableAzureAiReranking = true,
        });

        // Act
        var results = await client.SearchAsync(CreateScope(), "preferred database", topK: 2);

        // Assert
        Assert.Equal([2L, 1L], results.Select(result => result.Id));
        Assert.Equal(0.98, results[0].RerankerScore);
        Assert.Equal(0.63, results[1].RerankerScore);
    }

    [Fact]
    public async Task SearchAsync_WhenRerankingFails_ReturnsHybridOrderAsync()
    {
        // Arrange
        var candidates = new[]
        {
            CreateRecord(1, PostgresMemoryType.Fact, "First hybrid result."),
            CreateRecord(2, PostgresMemoryType.Fact, "Second hybrid result."),
            CreateRecord(3, PostgresMemoryType.Fact, "Third hybrid result."),
        };
        this._store
            .Setup(store => store.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<string>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(candidates);
        this._store
            .Setup(store => store.RerankAsync(
                It.IsAny<string>(),
                It.IsAny<IReadOnlyList<PostgresMemoryRecord>>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new NpgsqlException("Reranker unavailable."));
        var client = this.CreateClient(new PostgresMemoryClientOptions
        {
            AutoProcess = false,
            EnableAzureAiReranking = true,
        });

        // Act
        var results = await client.SearchAsync(CreateScope(), "database", topK: 2);

        // Assert
        Assert.Equal([1L, 2L], results.Select(result => result.Id));
        Assert.All(results, result => Assert.Null(result.RerankerScore));
    }

    [Fact]
    public async Task ExtractMemoriesAsync_StoresTypedMemoriesAndSkipsDuplicateAsync()
    {
        var turns = new[]
        {
            CreateRecord(1, PostgresMemoryType.Turn, "I prefer PostgreSQL.", role: "user", threadId: "thread"),
        };
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(turns);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(
                ChatRole.Assistant,
                """
                [
                  {"content":"Prefers PostgreSQL","memory_type":"fact","confidence":0.96},
                  {"content":"Show SQL first","memory_type":"procedural","confidence":0.88}
                ]
                """)));
        this._store
            .Setup(store => store.FindDuplicateAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Procedural,
                It.IsAny<string>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateRecord(9, PostgresMemoryType.Procedural, "Show SQL first"));
        var client = this.CreateClient();

        var inserted = await client.ExtractMemoriesAsync(CreateScope());

        Assert.Equal(1, inserted);
        this._store.Verify(
            store => store.InsertDerivedMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Fact,
                "Prefers PostgreSQL",
                0.96,
                null,
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                null,
                It.IsAny<CancellationToken>()),
            Times.Once);
        this._store.Verify(
            store => store.InsertDerivedMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Procedural,
                It.IsAny<string>(),
                It.IsAny<double>(),
                It.IsAny<double?>(),
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                It.IsAny<DateTimeOffset?>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task ExtractMemoriesAsync_AppliesEpisodicTimeToLiveAsync()
    {
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Turn, "The migration succeeded.", role: "user", threadId: "thread"),
            ]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(
                ChatRole.Assistant,
                """[{"content":"Migration succeeded after adding an index","memory_type":"episodic","confidence":0.9}]""")));
        var client = this.CreateClient(new PostgresMemoryClientOptions
        {
            AutoProcess = false,
            EpisodicMemoryTimeToLive = TimeSpan.FromDays(30),
        });

        _ = await client.ExtractMemoriesAsync(CreateScope());

        this._store.Verify(
            store => store.InsertDerivedMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Episodic,
                It.IsAny<string>(),
                It.IsAny<double>(),
                It.IsAny<double?>(),
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                It.Is<DateTimeOffset?>(value =>
                    value.HasValue && value.Value > DateTimeOffset.UtcNow.AddDays(29)),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task ExtractMemoriesAsync_MalformedResponseDoesNotAdvanceCheckpointAsync()
    {
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Turn, "Remember this.", role: "user", threadId: "thread"),
            ]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "not valid JSON")));
        var client = this.CreateClient();

        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ExtractMemoriesAsync(CreateScope()));

        this._store.Verify(
            store => store.UpsertProcessingStateAsync(
                It.IsAny<string>(),
                It.IsAny<ProcessingState>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Theory]
    [InlineData("Before []")]
    [InlineData("```json\n[]\n```")]
    [InlineData("[] after")]
    public async Task ExtractMemoriesAsync_RejectsSurroundingTextAsync(string responseText)
    {
        // Arrange
        this.SetupUnprocessedTurn();
        this.SetupChatResponse(responseText);
        var client = this.CreateClient();

        // Act
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ExtractMemoriesAsync(CreateScope()));

        // Assert
        this._store.Verify(
            store => store.UpsertProcessingStateAsync(
                It.IsAny<string>(),
                It.IsAny<ProcessingState>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task ExtractMemoriesAsync_RejectsPartiallyMalformedResponseAsync()
    {
        // Arrange
        this.SetupUnprocessedTurn();
        this.SetupChatResponse(
            """
            [
              {"content":"Valid memory","memory_type":"fact","confidence":0.9},
              {"content":"Missing confidence","memory_type":"procedural"}
            ]
            """);
        var client = this.CreateClient();

        // Act
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ExtractMemoriesAsync(CreateScope()));

        // Assert
        this._store.Verify(
            store => store.InsertDerivedMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<PostgresMemoryType>(),
                It.IsAny<string>(),
                It.IsAny<double>(),
                It.IsAny<double?>(),
                It.IsAny<IReadOnlyList<string>>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                It.IsAny<DateTimeOffset?>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Theory]
    [MemberData(nameof(InvalidExtractionResponses))]
    public async Task ExtractMemoriesAsync_RejectsInvalidItemFieldsAsync(string responseText)
    {
        // Arrange
        this.SetupUnprocessedTurn();
        this.SetupChatResponse(responseText);
        var client = this.CreateClient();

        // Act and assert
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ExtractMemoriesAsync(CreateScope()));
    }

    [Fact]
    public async Task DirectThreadOperations_ShareProcessingLockAsync()
    {
        // Arrange
        var firstEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var secondCallIssued = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var secondEntered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var releaseFirst = new ManualResetEventSlim();
        var callCount = 0;
        this._store
            .Setup(store => store.GetProcessingStateAsync(
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .Callback((string _, CancellationToken cancellationToken) =>
            {
                if (Interlocked.Increment(ref callCount) == 1)
                {
                    firstEntered.SetResult();
                    releaseFirst.Wait(cancellationToken);
                }
                else
                {
                    secondEntered.SetResult();
                }
            })
            .ReturnsAsync(default(ProcessingState));
        this._store
            .Setup(store => store.GetLatestSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Summary,
                It.IsAny<CancellationToken>()))
            .Callback(() => secondEntered.SetResult())
            .ReturnsAsync((null, 0L));
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<long>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        var client = this.CreateClient();

        // Act
        var first = Task.Run(() => client.ExtractMemoriesAsync(CreateScope()));
        await firstEntered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var second = Task.Run(async () =>
        {
            var operation = client.GenerateThreadSummaryAsync(CreateScope());
            secondCallIssued.SetResult();
            return await operation;
        });
        await secondCallIssued.Task.WaitAsync(TimeSpan.FromSeconds(5));

        // Assert
        Assert.False(secondEntered.Task.IsCompleted);

        releaseFirst.Set();
        await Task.WhenAll(first, second);
        Assert.True(secondEntered.Task.IsCompleted);
    }

    [Fact]
    public async Task GenerateThreadSummaryAsync_InsertsIncrementalSummaryAsync()
    {
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(5, PostgresMemoryType.Turn, "Use Postgres.", role: "user", threadId: "thread"),
            ]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "The user chose PostgreSQL.")));
        this._store
            .Setup(store => store.InsertSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Summary,
                It.IsAny<string>(),
                It.IsAny<ReadOnlyMemory<float>>(),
                5,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(10L);
        var client = this.CreateClient();

        var summary = await client.GenerateThreadSummaryAsync(CreateScope());

        Assert.NotNull(summary);
        Assert.Equal(PostgresMemoryType.Summary, summary.MemoryType);
        Assert.Equal("The user chose PostgreSQL.", summary.Content);
    }

    [Fact]
    public async Task GenerateThreadSummaryAsync_ReturnsLatestWhenInsertIsStaleAsync()
    {
        // Arrange
        var current = CreateRecord(11, PostgresMemoryType.Summary, "Current summary.", threadId: "thread");
        this._store
            .SetupSequence(store => store.GetLatestSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Summary,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((null, 0L))
            .ReturnsAsync((current, 6L));
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(5, PostgresMemoryType.Turn, "Use Postgres.", role: "user", threadId: "thread"),
            ]);
        this.SetupChatResponse("Generated summary.");
        this._store
            .Setup(store => store.InsertSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.Summary,
                "Generated summary.",
                It.IsAny<ReadOnlyMemory<float>>(),
                5,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(default(long?));
        var client = this.CreateClient();

        // Act
        var summary = await client.GenerateThreadSummaryAsync(CreateScope());

        // Assert
        Assert.Same(current, summary);
        this._store.Verify(
            store => store.UpsertProcessingStateAsync(
                It.IsAny<string>(),
                It.IsAny<ProcessingState>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task GenerateUserSummaryAsync_CapturesCutoffBeforeInputsAndModelAsync()
    {
        // Arrange
        var callOrder = new List<string>();
        this._store
            .Setup(store => store.GetTurnStatsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                false,
                It.IsAny<CancellationToken>()))
            .Callback(() => callOrder.Add("cutoff"))
            .ReturnsAsync((1, 7L));
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                100,
                0.5,
                It.IsAny<CancellationToken>()))
            .Callback(() => callOrder.Add("memories"))
            .ReturnsAsync(
            [
                CreateRecord(2, PostgresMemoryType.Fact, "Prefers PostgreSQL."),
            ]);
        this._store
            .Setup(store => store.GetRecentThreadSummariesAsync(
                It.IsAny<PostgresMemoryScope>(),
                25,
                It.IsAny<CancellationToken>()))
            .Callback(() => callOrder.Add("summaries"))
            .ReturnsAsync([]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback(() => callOrder.Add("model"))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "User profile.")));
        this._store
            .Setup(store => store.InsertSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.UserSummary,
                "User profile.",
                It.IsAny<ReadOnlyMemory<float>>(),
                7,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(20L);
        var client = this.CreateClient();

        // Act
        var summary = await client.GenerateUserSummaryAsync(CreateScope());

        // Assert
        Assert.NotNull(summary);
        Assert.Equal(["cutoff", "memories", "summaries", "model"], callOrder);
        this._store.Verify(
            store => store.UpsertProcessingStateAsync(
                It.IsAny<string>(),
                It.Is<ProcessingState>(state => state.UserSummaryThroughTurnId == 7),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task GenerateUserSummaryAsync_ReturnsLatestWhenInsertIsStaleAsync()
    {
        // Arrange
        var current = CreateRecord(21, PostgresMemoryType.UserSummary, "Current profile.");
        this._store
            .SetupSequence(store => store.GetLatestSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.UserSummary,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((null, 0L))
            .ReturnsAsync((current, 8L));
        this._store
            .Setup(store => store.GetTurnStatsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                false,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((1, 7L));
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                100,
                0.5,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(2, PostgresMemoryType.Fact, "Prefers PostgreSQL."),
            ]);
        this.SetupChatResponse("Generated profile.");
        this._store
            .Setup(store => store.InsertSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                PostgresMemoryType.UserSummary,
                "Generated profile.",
                It.IsAny<ReadOnlyMemory<float>>(),
                7,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(default(long?));
        var client = this.CreateClient();

        // Act
        var summary = await client.GenerateUserSummaryAsync(CreateScope());

        // Assert
        Assert.Same(current, summary);
        this._store.Verify(
            store => store.UpsertProcessingStateAsync(
                It.IsAny<string>(),
                It.IsAny<ProcessingState>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task ReconcileAsync_MarksOnlyValidContradictionsAsync()
    {
        var memories = new[]
        {
            CreateRecord(1, PostgresMemoryType.Fact, "User is vegetarian."),
            CreateRecord(2, PostgresMemoryType.Fact, "User eats steak."),
        };
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(memories);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(
                ChatRole.Assistant,
                """[{"superseded_id":1,"winner_id":2,"reason":"contradict"}]""")));
        var client = this.CreateClient();

        var reconciled = await client.ReconcileAsync(CreateScope());

        Assert.Equal(1, reconciled);
        this._store.Verify(
            store => store.MarkSupersededAsync(1, 2, "contradict", It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task ReconcileAsync_MalformedResponseThrowsAsync()
    {
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Fact, "User is vegetarian."),
                CreateRecord(2, PostgresMemoryType.Fact, "User eats steak."),
            ]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "not valid JSON")));
        var client = this.CreateClient();

        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ReconcileAsync(CreateScope()));

        this._store.Verify(
            store => store.MarkSupersededAsync(
                It.IsAny<long>(),
                It.IsAny<long>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Theory]
    [InlineData("Before []")]
    [InlineData("```json\n[]\n```")]
    [InlineData("[] after")]
    public async Task ReconcileAsync_RejectsSurroundingTextAsync(string responseText)
    {
        // Arrange
        this.SetupReconciliationMemories();
        this.SetupChatResponse(responseText);
        var client = this.CreateClient();

        // Act and assert
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ReconcileAsync(CreateScope()));
    }

    [Fact]
    public async Task ReconcileAsync_RejectsPartiallyMalformedResponseAsync()
    {
        // Arrange
        this.SetupReconciliationMemories();
        this.SetupChatResponse(
            """
            [
              {"superseded_id":1,"winner_id":2,"reason":"contradict"},
              {"superseded_id":2,"winner_id":1,"reason":" "}
            ]
            """);
        var client = this.CreateClient();

        // Act
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ReconcileAsync(CreateScope()));

        // Assert
        this._store.Verify(
            store => store.MarkSupersededAsync(
                It.IsAny<long>(),
                It.IsAny<long>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Theory]
    [MemberData(nameof(InvalidReconciliationResponses))]
    public async Task ReconcileAsync_RejectsInvalidItemFieldsAsync(string responseText)
    {
        // Arrange
        this.SetupReconciliationMemories();
        this.SetupChatResponse(responseText);
        var client = this.CreateClient();

        // Act and assert
        _ = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            client.ReconcileAsync(CreateScope()));
    }

    [Fact]
    public async Task ReconcileAsync_AcceptsEmptyArrayAsync()
    {
        // Arrange
        this.SetupReconciliationMemories();
        this.SetupChatResponse("[]");
        var client = this.CreateClient();

        // Act
        var reconciled = await client.ReconcileAsync(CreateScope());

        // Assert
        Assert.Equal(0, reconciled);
    }

    [Fact]
    public async Task ProcessNowAsync_UsesAlreadyLockedThreadCoresAsync()
    {
        // Arrange
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<long>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        var client = this.CreateClient();

        // Act and assert
        await client.ProcessNowAsync(CreateScope()).WaitAsync(TimeSpan.FromSeconds(5));
    }

    [Fact]
    public async Task AutoProcess_SchedulesBackgroundExtractionAndFlushWaitsAsync()
    {
        this._store
            .Setup(store => store.InsertTurnAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<ReadOnlyMemory<float>?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(1);
        this._store
            .Setup(store => store.GetTurnStatsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<long>(),
                true,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((1, 1L));
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<long>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Turn, "hello", role: "user", threadId: "thread"),
            ]);
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "[]")));
        var client = this.CreateClient(new PostgresMemoryClientOptions
        {
            AutoProcess = true,
            FactExtractionEveryNTurns = 1,
            ThreadSummaryEveryNTurns = 0,
            UserSummaryEveryNTurns = 0,
            ReconcileEveryNExtractions = 0,
        });

        _ = await client.UpsertMemoryAsync(CreateScope(), "user", "hello");
        await client.FlushAsync();

        this._chatClient.Verify(
            chat => chat.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    private PostgresMemoryClient CreateClient(PostgresMemoryClientOptions? options = null) =>
        new(
            this._store.Object,
            this._embeddingGenerator.Object,
            this._chatClient.Object,
            options ?? new PostgresMemoryClientOptions { AutoProcess = false });

    private static PostgresMemoryScope CreateScope() =>
        new() { ApplicationId = "app", AgentId = "agent", UserId = "user", ThreadId = "thread" };

    public static TheoryData<string> InvalidExtractionResponses =>
        new()
        {
            """[{"content":"Memory","memory_type":"fact"}]""",
            """[{"content":"Memory","memory_type":"fact","confidence":1.1}]""",
            """[{"content":"Memory","memory_type":"fact","confidence":1e400}]""",
            """[{"content":"Memory","memory_type":"fact","confidence":0.8,"salience":-0.1}]""",
            """[{"content":"Memory","memory_type":"fact","confidence":0.8,"tags":"tag"}]""",
            """[{"content":"Memory","memory_type":"fact","confidence":0.8,"tags":["ok"," "]}]""",
            """[{"content":" ","memory_type":"fact","confidence":0.8}]""",
            """[{"content":"Memory","memory_type":"summary","confidence":0.8}]""",
            """[1]""",
        };

    public static TheoryData<string> InvalidReconciliationResponses =>
        new()
        {
            """[{"superseded_id":1.0,"winner_id":2,"reason":"contradict"}]""",
            """[{"superseded_id":1,"winner_id":"2","reason":"contradict"}]""",
            """[{"superseded_id":1,"winner_id":2}]""",
            """[{"superseded_id":1,"winner_id":2,"reason":null}]""",
            """[1]""",
        };

    private void SetupUnprocessedTurn()
    {
        this._store
            .Setup(store => store.GetTurnsAfterAsync(
                It.IsAny<PostgresMemoryScope>(),
                0,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Turn, "Remember this.", role: "user", threadId: "thread"),
            ]);
    }

    private void SetupReconciliationMemories()
    {
        this._store
            .Setup(store => store.GetActiveMemoriesAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateRecord(1, PostgresMemoryType.Fact, "User is vegetarian."),
                CreateRecord(2, PostgresMemoryType.Fact, "User eats steak."),
            ]);
    }

    private void SetupChatResponse(string responseText)
    {
        this._chatClient
            .Setup(client => client.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, responseText)));
    }

    private static PostgresMemoryRecord CreateRecord(
        long id,
        PostgresMemoryType type,
        string content,
        string? role = null,
        string? threadId = null) =>
        new()
        {
            Id = id,
            MemoryType = type,
            Content = content,
            Role = role,
            UserId = "user",
            ThreadId = threadId,
            Confidence = type == PostgresMemoryType.Turn ? null : 0.9,
            CreatedAt = DateTimeOffset.UtcNow,
            UpdatedAt = DateTimeOffset.UtcNow,
        };
}
