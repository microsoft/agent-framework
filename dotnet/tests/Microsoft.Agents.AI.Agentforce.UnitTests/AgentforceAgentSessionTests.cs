// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Agentforce;

namespace Microsoft.Agents.AI.Agentforce.UnitTests;

public class AgentforceAgentSessionTests
{
    [Fact]
    public async Task DefaultConstructor_CreatesSessionWithNullServiceSessionId()
    {
        // Arrange & Act
        // Access via the agent to test the session creation flow.
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var agent = new AgentforceAgent(config);
        var session = await agent.CreateSessionAsync();

        // Assert
        var typedSession = Assert.IsType<AgentforceAgentSession>(session);
        Assert.Null(typedSession.ServiceSessionId);
        Assert.NotNull(typedSession.StateBag);
    }

    [Fact]
    public async Task SerializeAndDeserialize_PreservesSessionState()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var agent = new AgentforceAgent(config);
        var session = await agent.CreateSessionAsync();
        var typedSession = (AgentforceAgentSession)session;

        // Simulate a session ID being set after session creation (as would happen in RunCoreAsync).
        // Use reflection since ServiceSessionId has internal setter.
        typeof(AgentforceAgentSession)
            .GetProperty(nameof(AgentforceAgentSession.ServiceSessionId))!
            .SetValue(typedSession, "test-session-123");

        typedSession.StateBag.SetValue<string>("testKey", "testValue");

        // Act
        var serialized = await agent.SerializeSessionAsync(typedSession);
        var deserialized = await agent.DeserializeSessionAsync(serialized);

        // Assert
        var deserializedTyped = Assert.IsType<AgentforceAgentSession>(deserialized);
        Assert.Equal("test-session-123", deserializedTyped.ServiceSessionId);
        Assert.Equal("testValue", deserializedTyped.StateBag.GetValue<string>("testKey"));
    }

    [Fact]
    public async Task DeserializeSession_WithInvalidJson_Throws()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var agent = new AgentforceAgent(config);
        var invalidJson = JsonSerializer.SerializeToElement("not-an-object");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
            await agent.DeserializeSessionAsync(invalidJson));
    }

    [Fact]
    public async Task SerializeSession_WithIncompatibleSession_Throws()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var agent = new AgentforceAgent(config);
        var incompatibleSession = new TestSession();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await agent.SerializeSessionAsync(incompatibleSession));
    }

    private sealed class TestSession : AgentSession
    {
    }
}
