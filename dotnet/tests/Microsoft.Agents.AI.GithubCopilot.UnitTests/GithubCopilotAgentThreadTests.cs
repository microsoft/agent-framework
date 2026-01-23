// Copyright (c) Microsoft. All rights reserved.

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
    public void SessionId_IsInternalSet()
    {
        // Arrange
        const string Json = """{"sessionId":"test-value"}""";
        JsonDocument doc = JsonDocument.Parse(Json);

        // Act
        var thread = new GithubCopilotAgentThread(doc.RootElement);

        // Assert
        Assert.Equal("test-value", thread.SessionId);
    }

    [Fact]
    public void Constructor_RoundTrip_SerializationPreservesState()
    {
        // Arrange
        const string SessionId = "session-rt-001";
        GithubCopilotAgentThread originalThread = new() { SessionId = SessionId };

        // Act
        JsonElement serialized = originalThread.Serialize();
        GithubCopilotAgentThread deserializedThread = new(serialized);

        // Assert
        Assert.Equal(originalThread.SessionId, deserializedThread.SessionId);
    }

    [Fact]
    public void Deserialize_WithSessionId_DeserializesCorrectly()
    {
        // Arrange
        const string Json = """{"sessionId":"test-session-id"}""";
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
