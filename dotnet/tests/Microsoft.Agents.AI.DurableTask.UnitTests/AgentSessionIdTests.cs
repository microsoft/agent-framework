// Copyright (c) Microsoft. All rights reserved.

using Microsoft.DurableTask.Entities;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

public sealed class AgentSessionIdTests
{
    [Fact]
    public void ParseValidSessionId()
    {
        const string Name = "test-agent";
        const string Key = "12345";
        string sessionIdString = $"@dafx-{Name}@{Key}";
        AgentSessionId sessionId = AgentSessionId.Parse(sessionIdString);

        Assert.Equal(Name, sessionId.Name);
        Assert.Equal(Key, sessionId.Key);
    }

    [Fact]
    public void ParseInvalidSessionId()
    {
        const string InvalidSessionIdString = "@test-agent@12345"; // Missing "dafx-" prefix
        Assert.Throws<ArgumentException>(() => AgentSessionId.Parse(InvalidSessionIdString));
    }

    [Fact]
    public void FromEntityId()
    {
        const string Name = "test-agent";
        const string Key = "12345";

        EntityInstanceId entityId = new($"dafx-{Name}", Key);
        AgentSessionId sessionId = (AgentSessionId)entityId;

        Assert.Equal(Name, sessionId.Name);
        Assert.Equal(Key, sessionId.Key);
    }

    [Fact]
    public void FromInvalidEntityId()
    {
        const string Name = "test-agent";
        const string Key = "12345";

        EntityInstanceId entityId = new(Name, Key); // Missing "dafx-" prefix

        Assert.Throws<ArgumentException>(() =>
        {
            // This assignment should throw an exception because
            // the entity ID is not a valid agent session ID.
            AgentSessionId sessionId = entityId;
        });
    }

    // Ensures the 2-arg constructor treats the key as opaque and never re-interprets
    // it as a serialized session id, so the resulting Name always comes from the first
    // argument regardless of the key's shape.
    [Fact]
    public void ConstructorTreatsKeyAsOpaqueValue()
    {
        AgentSessionId sessionId = new("agentA", "@dafx-agentB@some-key");

        Assert.Equal("agentA", sessionId.Name);
        Assert.Equal("@dafx-agentB@some-key", sessionId.Key);
    }
}
