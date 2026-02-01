// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.FoundryMemory.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryMemoryProvider"/> constructor validation and serialization.
/// </summary>
/// <remarks>
/// Since <see cref="FoundryMemoryProvider"/> directly uses <see cref="Azure.AI.Projects.AIProjectClient"/>,
/// integration tests are used to verify the memory operations. These unit tests focus on:
/// - Constructor parameter validation
/// - Serialization and deserialization of provider state
/// </remarks>
public sealed class FoundryMemoryProviderTests
{
    [Fact]
    public void Constructor_Throws_WhenClientIsNull()
    {
        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            null!,
            new FoundryMemoryProviderScope { Scope = "test" },
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.Equal("client", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenScopeIsNull()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            testClient.Client,
            null!,
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.Equal("scope", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenScopeValueIsEmpty()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentException ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            testClient.Client,
            new FoundryMemoryProviderScope(),
            new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.StartsWith("The Scope property must be provided.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsMissing()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentException ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            testClient.Client,
            new FoundryMemoryProviderScope { Scope = "test" },
            new FoundryMemoryProviderOptions()));
        Assert.StartsWith("The MemoryStoreName option must be provided.", ex.Message);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsNull()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();

        // Act & Assert
        ArgumentException ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            testClient.Client,
            new FoundryMemoryProviderScope { Scope = "test" },
            null));
        Assert.StartsWith("The MemoryStoreName option must be provided.", ex.Message);
    }

    [Fact]
    public void DeserializingConstructor_Throws_WhenClientIsNull()
    {
        // Arrange - use source-generated JSON context
        JsonElement jsonElement = JsonSerializer.SerializeToElement(
            new TestState { Scope = new TestScope { Scope = "test" } },
            TestJsonContext.Default.TestState);

        // Act & Assert
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            null!,
            jsonElement,
            options: new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.Equal("client", ex.ParamName);
    }

    [Fact]
    public void DeserializingConstructor_Throws_WithEmptyJsonElement()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        JsonElement jsonElement = JsonDocument.Parse("{}").RootElement;

        // Act & Assert
        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => new FoundryMemoryProvider(
            testClient.Client,
            jsonElement,
            options: new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.StartsWith("The FoundryMemoryProvider state did not contain the required scope property.", ex.Message);
    }

    [Fact]
    public void DeserializingConstructor_Throws_WithMissingScopeValue()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        JsonElement jsonElement = JsonSerializer.SerializeToElement(
            new TestState { Scope = new TestScope() },
            TestJsonContext.Default.TestState);

        // Act & Assert
        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => new FoundryMemoryProvider(
            testClient.Client,
            jsonElement,
            options: new FoundryMemoryProviderOptions { MemoryStoreName = "store" }));
        Assert.StartsWith("The FoundryMemoryProvider state did not contain the required scope property.", ex.Message);
    }

    [Fact]
    public void Serialize_RoundTripsScope()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        FoundryMemoryProviderScope scope = new() { Scope = "user-456" };
        FoundryMemoryProvider sut = new(testClient.Client, scope, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Act
        JsonElement stateElement = sut.Serialize();
        using JsonDocument doc = JsonDocument.Parse(stateElement.GetRawText());

        // Assert (JSON uses camelCase naming policy)
        Assert.True(doc.RootElement.TryGetProperty("scope", out JsonElement scopeElement));
        Assert.Equal("user-456", scopeElement.GetProperty("scope").GetString());
    }

    [Fact]
    public void DeserializingConstructor_RestoresScope()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        FoundryMemoryProviderScope originalScope = new() { Scope = "restored-user-789" };
        FoundryMemoryProvider original = new(testClient.Client, originalScope, new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Act
        JsonElement serializedState = original.Serialize();
        FoundryMemoryProvider restored = new(testClient.Client, serializedState, options: new FoundryMemoryProviderOptions { MemoryStoreName = "my-store" });

        // Assert - serialize again to verify scope was restored
        JsonElement restoredState = restored.Serialize();
        using JsonDocument doc = JsonDocument.Parse(restoredState.GetRawText());
        Assert.True(doc.RootElement.TryGetProperty("scope", out JsonElement scopeElement));
        Assert.Equal("restored-user-789", scopeElement.GetProperty("scope").GetString());
    }
}
