// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

public sealed class DurableAgentThreadTests
{
    [Fact]
    public void BuiltInSerialization()
    {
        AgentSessionId sessionId = AgentSessionId.WithRandomKey("test-agent");
        AgentThread thread = new DurableAgentThread(sessionId);

        JsonElement serializedThread = thread.Serialize();

        // Expected format: "{\"sessionId\":\"@dafx-test-agent@<random-key>\"}"
        string expectedSerializedThread = $"{{\"sessionId\":\"@dafx-{sessionId.Name}@{sessionId.Key}\"}}";
        Assert.Equal(expectedSerializedThread, serializedThread.ToString());

        DurableAgentThread deserializedThread = DurableAgentThread.Deserialize(serializedThread);
        Assert.Equal(sessionId, deserializedThread.SessionId);
    }

    [Fact]
    public void STJSerialization()
    {
        AgentSessionId sessionId = AgentSessionId.WithRandomKey("test-agent");
        AgentThread thread = new DurableAgentThread(sessionId);

        // Need to specify the type explicitly because STJ, unlike other serializers,
        // does serialization based on the static type of the object, not the runtime type.
        string serializedThread = JsonSerializer.Serialize(thread, typeof(DurableAgentThread));

        // Expected format: "{\"sessionId\":\"@dafx-test-agent@<random-key>\"}"
        string expectedSerializedThread = $"{{\"sessionId\":\"@dafx-{sessionId.Name}@{sessionId.Key}\"}}";
        Assert.Equal(expectedSerializedThread, serializedThread);

        DurableAgentThread? deserializedThread = JsonSerializer.Deserialize<DurableAgentThread>(serializedThread);
        Assert.NotNull(deserializedThread);
        Assert.Equal(sessionId, deserializedThread.SessionId);
    }
}
