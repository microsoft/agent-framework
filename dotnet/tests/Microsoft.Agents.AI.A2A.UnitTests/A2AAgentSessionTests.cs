// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgentSession"/> class.
/// </summary>
public sealed class A2AAgentSessionTests
{
    [Fact]
    public void Constructor_RoundTrip_SerializationPreservesState()
    {
        // Arrange
        const string ContextId = "context-rt-001";
        const string TaskId = "task-rt-002";

        A2AAgentSession originalSession = new() { ContextId = ContextId, TaskId = TaskId };

        // Act
        JsonElement serialized = originalSession.Serialize();

        A2AAgentSession deserializedSession = A2AAgentSession.Deserialize(serialized);

        // Assert
        Assert.Equal(originalSession.ContextId, deserializedSession.ContextId);
        Assert.Equal(originalSession.TaskId, deserializedSession.TaskId);
    }

    [Fact]
    public void Constructor_RoundTrip_SerializationPreservesStateBag()
    {
        // Arrange
        A2AAgentSession originalSession = new() { ContextId = "ctx-1", TaskId = "task-1" };
        originalSession.StateBag.SetValue("testKey", "testValue");

        // Act
        JsonElement serialized = originalSession.Serialize();
        A2AAgentSession deserializedSession = A2AAgentSession.Deserialize(serialized);

        // Assert
        Assert.Equal("ctx-1", deserializedSession.ContextId);
        Assert.Equal("task-1", deserializedSession.TaskId);
        Assert.True(deserializedSession.StateBag.TryGetValue<string>("testKey", out var value));
        Assert.Equal("testValue", value);
    }
}
