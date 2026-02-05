// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Tests for <see cref="ServiceIdAgentSession"/>.
/// </summary>
public class ServiceIdAgentSessionTests
{
    #region Constructor and Property Tests  

    [Fact]
    public void Constructor_SetsDefaults()
    {
        // Arrange & Act
        var session = new TestServiceIdAgentSession();

        // Assert
        Assert.Null(session.GetServiceSessionId());
    }

    [Fact]
    public void Constructor_WithServiceSessionId_SetsProperty()
    {
        // Arrange & Act
        var session = new TestServiceIdAgentSession("service-id-123");

        // Assert
        Assert.Equal("service-id-123", session.GetServiceSessionId());
    }

    [Fact]
    public void Constructor_WithSerializedId_SetsProperty()
    {
        // Arrange
        var serviceSessionWrapper = new ServiceIdAgentSession.ServiceIdAgentSessionState { ServiceSessionId = "service-id-456" };
        var json = JsonSerializer.SerializeToElement(serviceSessionWrapper, TestJsonSerializerContext.Default.ServiceIdAgentSessionState);

        // Act
        var session = new TestServiceIdAgentSession(json);

        // Assert
        Assert.Equal("service-id-456", session.GetServiceSessionId());
    }

    [Fact]
    public void Constructor_WithSerializedUndefinedId_SetsProperty()
    {
        // Arrange
        var emptyObject = new EmptyObject();
        var json = JsonSerializer.SerializeToElement(emptyObject, TestJsonSerializerContext.Default.EmptyObject);

        // Act
        var session = new TestServiceIdAgentSession(json);

        // Assert
        Assert.Null(session.GetServiceSessionId());
    }

    [Fact]
    public void Constructor_WithInvalidJson_ThrowsArgumentException()
    {
        // Arrange
        var invalidJson = JsonSerializer.SerializeToElement(42, TestJsonSerializerContext.Default.Int32);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new TestServiceIdAgentSession(invalidJson));
    }

    #endregion

    #region SerializeAsync Tests

    [Fact]
    public void Serialize_ReturnsCorrectJson_WhenServiceSessionIdIsSet()
    {
        // Arrange
        var session = new TestServiceIdAgentSession("service-id-789");

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.True(json.TryGetProperty("serviceSessionId", out var idProperty));
        Assert.Equal("service-id-789", idProperty.GetString());
    }

    [Fact]
    public void Serialize_ReturnsUndefinedServiceSessionId_WhenNotSet()
    {
        // Arrange
        var session = new TestServiceIdAgentSession();

        // Act
        var json = session.Serialize();

        // Assert
        Assert.Equal(JsonValueKind.Object, json.ValueKind);
        Assert.False(json.TryGetProperty("serviceSessionId", out _));
    }

    #endregion

    // Sealed test subclass to expose protected members for testing
    private sealed class TestServiceIdAgentSession : ServiceIdAgentSession
    {
        public TestServiceIdAgentSession() { }
        public TestServiceIdAgentSession(string serviceSessionId) : base(serviceSessionId) { }
        public TestServiceIdAgentSession(JsonElement serializedSessionState) : base(serializedSessionState) { }
        public string? GetServiceSessionId() => this.ServiceSessionId;
    }

    // Helper class to represent empty objects
    internal sealed class EmptyObject;
}
