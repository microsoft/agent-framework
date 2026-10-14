// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Memory;

/// <summary>
/// Tests for <see cref="FoundryMemoryProvider"/>.
/// </summary>
/// <remarks>
/// A mocked HTTP transport lets these tests exercise the public provider invocation without a live Foundry project.
/// These unit tests cover:
/// - Constructor parameter validation
/// - State initializer validation
/// - Memory search result handling
/// </remarks>
public sealed class FoundryMemoryProviderTests
{
    [Theory]
    [InlineData("""{"memories":[]}""")]
    [InlineData("""{"memories":[{"memory_item":{"content":""}},{"memory_item":{"content":"   "}}]}""")]
    public async Task InvokingAsync_WhenSearchReturnsNoUsableMemories_ReturnsOnlyInputMessagesAsync(string searchResponse)
    {
        // Arrange
        using TestableAIProjectClient testClient = new(searchMemoriesResponse: searchResponse);
        Mock<ILoggerFactory> loggerFactory = CreateErrorFailingLoggerFactory();
        FoundryMemoryProvider sut = new(
            testClient.Client,
            "store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test")),
            loggerFactory: loggerFactory.Object);
        AIContextProvider.InvokingContext invocation = CreateInvokingContext();

        // Act
        AIContext result = await sut.InvokingAsync(invocation);

        // Assert
        Assert.Contains(
            "/memory_stores/store:search_memories",
            testClient.Handler.LastRequestUri!,
            StringComparison.Ordinal);
        ChatMessage message = Assert.Single(result.Messages!);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("What do I prefer?", message.Text);
    }

    [Fact]
    public async Task InvokingAsync_WhenSearchReturnsMemories_InjectsMemoryMessageAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new(
            searchMemoriesResponse:
                """
                {
                  "search_id": "search-1",
                  "memories": [
                    {
                      "memory_item": {
                        "memory_id": "memory-1",
                        "updated_at": 0,
                        "scope": "test",
                        "content": "The user prefers concise answers.",
                        "kind": "user_profile"
                      }
                    }
                  ]
                }
                """);
        FoundryMemoryProvider sut = new(
            testClient.Client,
            "store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test")));
        AIContextProvider.InvokingContext invocation = CreateInvokingContext();

        // Act
        AIContext result = await sut.InvokingAsync(invocation);

        // Assert
        ChatMessage[] messages = result.Messages!.ToArray();
        Assert.Equal(2, messages.Length);
        Assert.Equal("What do I prefer?", messages[0].Text);
        Assert.Equal(ChatRole.User, messages[1].Role);
        Assert.Equal(
            "## Memories\nConsider the following memories when answering user questions:\nThe user prefers concise answers.",
            messages[1].Text);
    }

    [Fact]
    public void Constructor_Throws_WhenClientIsNull()
    {
        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            null!,
            "store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("client", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenStateInitializerIsNull()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            testClient.Client,
            "store",
            stateInitializer: null!));
        Assert.Equal("stateInitializer", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsEmpty()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentException ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            testClient.Client,
            "",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("memoryStoreName", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsNull()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            testClient.Client,
            null!,
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("memoryStoreName", ex.ParamName);
    }

    [Fact]
    public void Scope_Throws_WhenScopeIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProviderScope(null!));
    }

    [Fact]
    public void Scope_Throws_WhenScopeIsEmpty()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new FoundryMemoryProviderScope(""));
    }

    [Fact]
    public void StateInitializer_Throws_WhenScopeIsNull()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        FoundryMemoryProvider sut = new(
            testClient.Client,
            "store",
            stateInitializer: _ => new(null!));

        // Act & Assert - state initializer validation is deferred to first use
        Assert.Throws<ArgumentNullException>(() =>
        {
            // Force state initialization by creating a session-like scenario
            // The validation happens inside the ValidateStateInitializer wrapper
            try
            {
                // The stateInitializer wraps with validation, so calling it will throw
                var field = typeof(FoundryMemoryProvider).GetField("_sessionState", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                var sessionState = field!.GetValue(sut);
                var method = sessionState!.GetType().GetMethod("GetOrInitializeState");
                method!.Invoke(sessionState, [null]);
            }
            catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException is not null)
            {
                throw tie.InnerException;
            }
        });
    }

    [Fact]
    public void Constructor_Succeeds_WithValidParameters()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act
        FoundryMemoryProvider sut = new(
            testClient.Client,
            "my-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("user-456")));

        // Assert
        Assert.NotNull(sut);
    }

    private static AIContextProvider.InvokingContext CreateInvokingContext() => new(
        new Mock<AIAgent>().Object,
        new Mock<AgentSession>().Object,
        new AIContext { Messages = [new ChatMessage(ChatRole.User, "What do I prefer?")] });

    private static Mock<ILoggerFactory> CreateErrorFailingLoggerFactory()
    {
        Mock<ILogger> mockLogger = new(MockBehavior.Strict);
        mockLogger.Setup(logger => logger.IsEnabled(LogLevel.Information)).Returns(false);
        mockLogger.Setup(logger => logger.IsEnabled(LogLevel.Error)).Returns(true);

        Mock<ILoggerFactory> loggerFactory = new(MockBehavior.Strict);
        loggerFactory.Setup(factory => factory.CreateLogger(It.IsAny<string>())).Returns(mockLogger.Object);

        return loggerFactory;
    }
}
