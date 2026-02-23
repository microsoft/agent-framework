// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.FoundryMemory.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryMemoryProvider"/> constructor validation.
/// </summary>
/// <remarks>
/// Since <see cref="FoundryMemoryProvider"/> directly uses <see cref="Azure.AI.Projects.AIProjectClient"/>,
/// integration tests are used to verify the memory operations. These unit tests focus on:
/// - Constructor parameter validation
/// - State initializer validation
/// </remarks>
public sealed class FoundryMemoryProviderTests
{
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
}
