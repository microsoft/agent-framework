// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AContinuationToken"/> class.
/// </summary>
public sealed class A2AContinuationTokenTests
{
    [Fact]
    public void Constructor_WithValidTaskId_InitializesTaskIdProperty()
    {
        // Arrange
        const string TaskId = "task-123";

        // Act
        var token = new A2AContinuationToken(TaskId);

        // Assert
        Assert.Equal(TaskId, token.TaskId);
    }

    [Fact]
    public void ToBytes_WithValidToken_SerializesToJsonBytes()
    {
        // Arrange
        const string TaskId = "task-456";
        var token = new A2AContinuationToken(TaskId);

        // Act
        var bytes = token.ToBytes();

        // Assert
        Assert.NotEqual(0, bytes.Length);
        var jsonString = System.Text.Encoding.UTF8.GetString(bytes.ToArray());
        using var jsonDoc = JsonDocument.Parse(jsonString);
        var root = jsonDoc.RootElement;
        Assert.True(root.TryGetProperty("taskId", out var taskIdElement));
        Assert.Equal(TaskId, taskIdElement.GetString());
    }

    [Fact]
    public void FromToken_WithA2AContinuationToken_ReturnsSameInstance()
    {
        // Arrange
        const string TaskId = "task-direct";
        var originalToken = new A2AContinuationToken(TaskId);

        // Act
        var resultToken = A2AContinuationToken.FromToken(originalToken);

        // Assert
        Assert.Same(originalToken, resultToken);
        Assert.Equal(TaskId, resultToken.TaskId);
    }

    [Fact]
    public void FromToken_WithSerializedToken_DeserializesCorrectly()
    {
        // Arrange
        const string TaskId = "task-deserialized";
        var originalToken = new A2AContinuationToken(TaskId);
        var serialized = originalToken.ToBytes();

        // Create a mock token wrapper to pass to FromToken
        var mockToken = new MockResponseContinuationToken(serialized);

        // Act
        var resultToken = A2AContinuationToken.FromToken(mockToken);

        // Assert
        Assert.Equal(TaskId, resultToken.TaskId);
        Assert.IsType<A2AContinuationToken>(resultToken);
    }

    [Fact]
    public void FromToken_RoundTrip_PreservesTaskId()
    {
        // Arrange
        const string TaskId = "task-roundtrip-123";
        var originalToken = new A2AContinuationToken(TaskId);
        var serialized = originalToken.ToBytes();
        var mockToken = new MockResponseContinuationToken(serialized);

        // Act
        var deserializedToken = A2AContinuationToken.FromToken(mockToken);
        var reserialized = deserializedToken.ToBytes();
        var mockToken2 = new MockResponseContinuationToken(reserialized);
        var deserializedAgain = A2AContinuationToken.FromToken(mockToken2);

        // Assert
        Assert.Equal(TaskId, deserializedAgain.TaskId);
    }

    [Fact]
    public void FromToken_WithEmptyData_ThrowsArgumentException()
    {
        // Arrange
        var emptyToken = new MockResponseContinuationToken(ReadOnlyMemory<byte>.Empty);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => A2AContinuationToken.FromToken(emptyToken));
    }

    [Fact]
    public void FromToken_WithMissingTaskIdProperty_ThrowsException()
    {
        // Arrange
        var jsonWithoutTaskId = System.Text.Encoding.UTF8.GetBytes("{ \"someOtherProperty\": \"value\" }").AsMemory();
        var mockToken = new MockResponseContinuationToken(jsonWithoutTaskId);

        // Act & Assert
        Assert.Throws<JsonException>(() => A2AContinuationToken.FromToken(mockToken));
    }

    [Fact]
    public void FromToken_WithValidTaskId_ParsesTaskIdCorrectly()
    {
        // Arrange
        const string TaskId = "task-multi-prop";
        var json = System.Text.Encoding.UTF8.GetBytes($"{{ \"taskId\": \"{TaskId}\" }}").AsMemory();
        var mockToken = new MockResponseContinuationToken(json);

        // Act
        var resultToken = A2AContinuationToken.FromToken(mockToken);

        // Assert
        Assert.Equal(TaskId, resultToken.TaskId);
    }

    /// <summary>
    /// Mock implementation of ResponseContinuationToken for testing.
    /// </summary>
    private sealed class MockResponseContinuationToken : ResponseContinuationToken
    {
        private readonly ReadOnlyMemory<byte> _data;

        public MockResponseContinuationToken(ReadOnlyMemory<byte> data)
        {
            this._data = data;
        }

        public override ReadOnlyMemory<byte> ToBytes()
        {
            return this._data;
        }
    }
}
