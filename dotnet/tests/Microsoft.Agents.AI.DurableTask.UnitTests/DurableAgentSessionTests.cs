// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

public sealed class DurableAgentSessionTests
{
    [Fact]
    public void BuiltInSerialization()
    {
        AgentSessionId sessionId = AgentSessionId.WithRandomKey("test-agent");
        DurableAgentSession session = new(sessionId);

        JsonElement serializedSession = session.Serialize();

        // Expected format: "{\"sessionId\":\"@dafx-test-agent@<random-key>\"}"
        string expectedSerializedSession = $"{{\"sessionId\":\"@dafx-{sessionId.Name}@{sessionId.Key}\"}}";
        Assert.Equal(expectedSerializedSession, serializedSession.ToString());

        DurableAgentSession deserializedSession = DurableAgentSession.Deserialize(serializedSession);
        Assert.Equal(sessionId, deserializedSession.SessionId);
    }

    [Fact]
    public void STJSerialization()
    {
        AgentSessionId sessionId = AgentSessionId.WithRandomKey("test-agent");
        AgentSession session = new DurableAgentSession(sessionId);

        // Need to specify the type explicitly because STJ, unlike other serializers,
        // does serialization based on the static type of the object, not the runtime type.
        string serializedSession = JsonSerializer.Serialize(session, typeof(DurableAgentSession));

        // Expected format: "{\"sessionId\":\"@dafx-test-agent@<random-key>\"}"
        string expectedSerializedSession = $"{{\"sessionId\":\"@dafx-{sessionId.Name}@{sessionId.Key}\"}}";
        Assert.Equal(expectedSerializedSession, serializedSession);

        DurableAgentSession? deserializedSession = JsonSerializer.Deserialize<DurableAgentSession>(serializedSession);
        Assert.NotNull(deserializedSession);
        Assert.Equal(sessionId, deserializedSession.SessionId);
    }
}
