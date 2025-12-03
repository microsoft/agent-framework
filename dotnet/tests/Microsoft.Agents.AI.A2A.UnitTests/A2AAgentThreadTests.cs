// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgentThread"/> class.
/// </summary>
public sealed class A2AAgentThreadTests
{
    [Fact]
    public void Constructor_RoundTrip_SerializationPreservesState()
    {
        // Arrange
        const string ContextId = "context-rt-001";
        const string TaskId = "task-rt-002";

        A2AAgentThread originalThread = new() { ContextId = ContextId, TaskId = TaskId };

        // Act
        JsonElement serialized = originalThread.Serialize();

        A2AAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Equal(originalThread.ContextId, deserializedThread.ContextId);
        Assert.Equal(originalThread.TaskId, deserializedThread.TaskId);
    }
}
