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
}
