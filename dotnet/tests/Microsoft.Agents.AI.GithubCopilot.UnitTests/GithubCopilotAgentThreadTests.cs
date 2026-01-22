// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.GithubCopilot.UnitTests;

/// <summary>
/// Unit tests for the <see cref="GithubCopilotAgentThread"/> class.
/// </summary>
public sealed class GithubCopilotAgentThreadTests
{
    [Fact]
    public void Constructor_InitializesWithNullSessionId()
    {
        // Act
        var thread = new GithubCopilotAgentThread();

        // Assert
        Assert.Null(thread.SessionId);
    }

    [Fact]
    public void SessionId_CanBeSetAndRetrieved()
    {
        // Arrange
        var thread = new GithubCopilotAgentThread();
        const string TestSessionId = "test-session-id";

        // Act
        thread.SessionId = TestSessionId;

        // Assert
        Assert.Equal(TestSessionId, thread.SessionId);
    }

    [Fact]
    public void Constructor_RoundTrip_SerializationPreservesState()
    {
        // Arrange
        const string SessionId = "session-rt-001";
        GithubCopilotAgentThread originalThread = new() { SessionId = SessionId };

        // Act
        JsonElement serialized = originalThread.Serialize();

        // Debug output
        Console.WriteLine($"Serialized JSON: {serialized.GetRawText()}");

        GithubCopilotAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Equal(originalThread.SessionId, deserializedThread.SessionId);
    }

    [Fact]
    public void Deserialize_WithSessionId_DeserializesCorrectly()
    {
        // Arrange
        const string Json = """{"SessionId":"test-session-id"}""";
        JsonDocument doc = JsonDocument.Parse(Json);

        // Act
        var thread = new GithubCopilotAgentThread(doc.RootElement);

        // Assert
        Assert.Equal("test-session-id", thread.SessionId);
    }

    [Fact]
    public void Deserialize_WithoutSessionId_HasNullSessionId()
    {
        // Arrange
        const string Json = """{}""";
        JsonDocument doc = JsonDocument.Parse(Json);

        // Act
        var thread = new GithubCopilotAgentThread(doc.RootElement);

        // Assert
        Assert.Null(thread.SessionId);
    }
}
