// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.ObjectModel;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

public class AIContextProviderTests
{
    [Fact]
    public async Task InvokedAsync_ReturnsCompletedTaskAsync()
    {
        var provider = new TestAIContextProvider();
        var messages = new ReadOnlyCollection<ChatMessage>([]);
        var task = provider.InvokedAsync(new(messages, aiContextProviderMessages: null));
        Assert.Equal(default, task);
    }

    [Fact]
    public void Serialize_ReturnsEmptyElement()
    {
        var provider = new TestAIContextProvider();
        var actual = provider.Serialize();
        Assert.Equal(default, actual);
    }

    [Fact]
    public void InvokingContext_Constructor_ThrowsForNullMessages()
    {
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokingContext(null!));
    }

    [Fact]
    public void InvokedContext_Constructor_ThrowsForNullMessages()
    {
        Assert.Throws<ArgumentNullException>(() => new AIContextProvider.InvokedContext(null!, aiContextProviderMessages: null));
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the exact context provider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingExactContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns the context provider itself when requesting the base AIContextProvider type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIContextProviderType_ReturnsContextProvider()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(AIContextProvider));

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting an unrelated type.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnrelatedType_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns null when a service key is provided, even for matching types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService(typeof(TestAIContextProvider), "some-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService throws ArgumentNullException when serviceType is null.
    /// </summary>
    [Fact]
    public void GetService_WithNullServiceType_ThrowsArgumentNullException()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => contextProvider.GetService(null!));
    }

    /// <summary>
    /// Verify that GetService generic method works correctly.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsCorrectType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<TestAIContextProvider>();

        // Assert
        Assert.NotNull(result);
        Assert.Same(contextProvider, result);
    }

    /// <summary>
    /// Verify that GetService generic method returns null for unrelated types.
    /// </summary>
    [Fact]
    public void GetService_Generic_ReturnsNullForUnrelatedType()
    {
        // Arrange
        var contextProvider = new TestAIContextProvider();

        // Act
        var result = contextProvider.GetService<string>();

        // Assert
        Assert.Null(result);
    }

    #endregion

    private sealed class TestAIContextProvider : AIContextProvider
    {
        public override ValueTask<AIContext> InvokingAsync(InvokingContext context, CancellationToken cancellationToken = default)
        {
            return default;
        }

        public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        {
            return base.Serialize(jsonSerializerOptions);
        }
    }
}
