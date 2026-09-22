// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.Postgres.UnitTests;

/// <summary>
/// Tests for <see cref="PostgresMemoryContextProvider"/>.
/// </summary>
public sealed class PostgresMemoryContextProviderTests
{
    private static readonly AIAgent s_agent = new Mock<AIAgent>().Object;
    private readonly Mock<IPostgresMemoryClient> _memoryClient = new();

    public PostgresMemoryContextProviderTests()
    {
        this._memoryClient
            .Setup(client => client.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<string>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync([]);
        this._memoryClient
            .Setup(client => client.GetUserSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((PostgresMemoryRecord?)null);
    }

    [Fact]
    public void Constructor_ThrowsForNullStateInitializer()
    {
        var exception = Assert.Throws<ArgumentNullException>(() =>
            new PostgresMemoryContextProvider(this._memoryClient.Object, null!));

        Assert.Contains("stateInitializer", exception.Message);
    }

    [Fact]
    public async Task InvokingAsync_RejectsStateWithoutUserAndThreadAsync()
    {
        var provider = new PostgresMemoryContextProvider(
            this._memoryClient.Object,
            _ => new PostgresMemoryContextProvider.State(new PostgresMemoryScope { UserId = "user" }));

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            provider.InvokingAsync(CreateInvokingContext("hello")).AsTask());
    }

    [Fact]
    public void State_DefaultSearchScopeIsCrossThread()
    {
        var storage = new PostgresMemoryScope
        {
            ApplicationId = "app",
            AgentId = "agent",
            UserId = "user",
            ThreadId = "thread",
        };

        var state = new PostgresMemoryContextProvider.State(storage);

        Assert.Equal("user", state.SearchScope.UserId);
        Assert.Null(state.SearchScope.ThreadId);
        Assert.Equal("app", state.SearchScope.ApplicationId);
        Assert.Equal("agent", state.SearchScope.AgentId);
    }

    [Fact]
    public async Task InvokingAsync_InjectsTypedMemoriesAndConfidenceAsync()
    {
        this._memoryClient
            .Setup(client => client.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                "What do you know about me?",
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                5,
                0.7,
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(
            [
                CreateMemory(PostgresMemoryType.Fact, "Prefers PostgreSQL", 0.95),
                CreateMemory(PostgresMemoryType.Procedural, "Show code before explanation", 0.84),
            ]);

        var provider = CreateProvider(this._memoryClient.Object);
        var result = await provider.InvokingAsync(CreateInvokingContext("What do you know about me?"));

        var messages = result.Messages!.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Contains("[fact] Prefers PostgreSQL (confidence: 0.95)", messages[1].Text);
        Assert.Contains("[procedural] Show code before explanation (confidence: 0.84)", messages[1].Text);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, messages[1].GetAgentRequestMessageSourceType());
    }

    [Fact]
    public async Task InvokingAsync_InjectsUserSummaryWhenSearchFailsAsync()
    {
        this._memoryClient
            .Setup(client => client.SearchAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<string>(),
                It.IsAny<IReadOnlyList<PostgresMemoryType>>(),
                It.IsAny<int>(),
                It.IsAny<double>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(new InvalidOperationException("search failed"));
        this._memoryClient
            .Setup(client => client.GetUserSummaryAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(CreateMemory(PostgresMemoryType.UserSummary, "Prefers concise answers"));

        var loggerFactory = new Mock<ILoggerFactory>();
        loggerFactory.Setup(factory => factory.CreateLogger(It.IsAny<string>()))
            .Returns(new Mock<ILogger>().Object);
        var provider = CreateProvider(this._memoryClient.Object, loggerFactory.Object);

        var result = await provider.InvokingAsync(CreateInvokingContext("hello"));

        var messages = result.Messages!.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Contains("untrusted reference information", messages[1].Text);
        Assert.Contains("Prefers concise answers", messages[1].Text);
    }

    [Fact]
    public async Task InvokedAsync_StoresOnlySupportedNonEmptyRolesAsync()
    {
        var provider = CreateProvider(this._memoryClient.Object);
        var context = new AIContextProvider.InvokedContext(
            s_agent,
            new TestAgentSession(),
            [
                new ChatMessage(ChatRole.User, "user"),
                new ChatMessage(ChatRole.System, "system"),
                new ChatMessage(ChatRole.Tool, "tool"),
                new ChatMessage(ChatRole.User, " "),
            ],
            [new ChatMessage(ChatRole.Assistant, "assistant")]);

        await provider.InvokedAsync(context);

        this._memoryClient.Verify(
            client => client.UpsertMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                It.IsAny<string>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Exactly(3));
        this._memoryClient.Verify(
            client => client.UpsertMemoryAsync(
                It.IsAny<PostgresMemoryScope>(),
                "tool",
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()),
            Times.Never);
    }

    [Fact]
    public async Task FlushAsync_DelegatesToMemoryClientAsync()
    {
        var provider = CreateProvider(this._memoryClient.Object);

        await provider.FlushAsync();

        this._memoryClient.Verify(
            client => client.FlushAsync(It.IsAny<CancellationToken>()),
            Times.Once);
    }

    [Fact]
    public async Task ProcessNowAsync_ResolvesSessionStateAndDelegatesAsync()
    {
        // Arrange
        var provider = CreateProvider(this._memoryClient.Object);
        var session = new TestAgentSession();
        using var cancellationSource = new CancellationTokenSource();

        // Act
        await provider.ProcessNowAsync(session, cancellationSource.Token);

        // Assert
        this._memoryClient.Verify(
            client => client.ProcessNowAsync(
                It.Is<PostgresMemoryScope>(scope =>
                    scope.UserId == "user" && scope.ThreadId == "thread"),
                cancellationSource.Token),
            Times.Once);
    }

    private static PostgresMemoryContextProvider CreateProvider(
        IPostgresMemoryClient client,
        ILoggerFactory? loggerFactory = null) =>
        new(
            client,
            _ => new PostgresMemoryContextProvider.State(
                new PostgresMemoryScope { UserId = "user", ThreadId = "thread" }),
            loggerFactory: loggerFactory);

    private static AIContextProvider.InvokingContext CreateInvokingContext(string text) =>
        new(
            s_agent,
            new TestAgentSession(),
            new AIContext { Messages = [new ChatMessage(ChatRole.User, text)] });

    private static PostgresMemoryRecord CreateMemory(
        PostgresMemoryType type,
        string content,
        double? confidence = null) =>
        new()
        {
            Id = 1,
            MemoryType = type,
            Content = content,
            UserId = "user",
            Confidence = confidence,
            CreatedAt = DateTimeOffset.UtcNow,
            UpdatedAt = DateTimeOffset.UtcNow,
        };

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
            this.StateBag = new AgentSessionStateBag();
        }
    }
}
