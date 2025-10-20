// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="ServiceIdAgentThread"/>.
/// </summary>
public class ServiceIdAgentThreadTests
{
    #region Constructor and Property Tests  

    [Fact]
    public void Constructor_SetsDefaults()
    {
        // Arrange & Act
        var thread = new TestServiceIdAgentThread();

        // Assert
        Assert.Null(thread.GetServiceThreadId());
    }

    [Fact]
    public void Constructor_WithServiceThreadId_SetsProperty()
    {
        // Arrange & Act
        var thread = new TestServiceIdAgentThread("service-id-123");

        // Assert
        Assert.Equal("service-id-123", thread.GetServiceThreadId());
    }

    [Fact]
    public void Constructor_WithSerializedId_SetsProperty()
    {
        // Arrange
        var serviceThreadWrapper = new ServiceIdAgentThread.ServiceIdAgentThreadState { ServiceThreadId = "service-id-456" };
        var json = JsonSerializer.SerializeToElement(serviceThreadWrapper, TestJsonSerializerContext.Default.ServiceIdAgentThreadState);

        // Act
        var thread = new TestServiceIdAgentThread(json);

        // Assert
        Assert.Equal("service-id-456", thread.GetServiceThreadId());
    }

    [Fact]
    public void Constructor_WithSerializedUndefinedId_SetsProperty()
    {
        // Arrange
        var emptyObject = new EmptyObject();
        var json = JsonSerializer.SerializeToElement(emptyObject, TestJsonSerializerContext.Default.EmptyObject);

        // Act
        var thread = new TestServiceIdAgentThread(json);

        // Assert
        Assert.Null(thread.GetServiceThreadId());
    }

    [Fact]
    public void Constructor_WithInvalidJson_ThrowsArgumentException()
    {
        // Arrange
        var invalidJson = JsonSerializer.SerializeToElement(42, TestJsonSerializerContext.Default.Int32);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TestServiceIdAgentThread(invalidJson));
    }

    #endregion

    #region SerializeAsync Tests

    [Fact]
    public void Serialize_ReturnsCorrectJson_WhenServiceThreadIdIsSet()
    {
        // Arrange
        var thread = new TestServiceIdAgentThread("service-id-789");

        // Act
        var json = thread.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("serviceThreadId", out var idProperty));
        Assert.Equal("service-id-789", idProperty.GetString());
    }

    [Fact]
    public void Serialize_ReturnsUndefinedServiceThreadId_WhenNotSet()
    {
        // Arrange
        var thread = new TestServiceIdAgentThread();

        // Act
        var json = thread.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.False(json.TryGetProperty("serviceThreadId", out _));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestServiceIdAgentThread : ServiceIdAgentThread
    {
        public TestServiceIdAgentThread() { }
        public TestServiceIdAgentThread(string serviceThreadId) : base(serviceThreadId) { }
        public TestServiceIdAgentThread(JsonElement serializedThreadState) : base(serializedThreadState) { }
        public string? GetServiceThreadId() => this.ServiceThreadId;
    }

    // Helper class to represent empty objects
    internal sealed class EmptyObject
    {
    }
}
