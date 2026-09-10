// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class InMemoryAgentSessionStoreTests
{
    [Fact]
    public async Task SaveSessionAsync_CompositeIdentifiersPreserveBoundariesAsync()
    {
        // Arrange: these identifier tuples collapse to the same colon-delimited string key.
        var store = new InMemoryAgentSessionStore();
        var agent = new TestAgent("concierge");

        // Act
        await store.SaveSessionAsync(agent, "delta", new TestSession("first"), "bravo:c-charlie");
        await store.SaveSessionAsync(agent, "charlie:c-delta", new TestSession("second"), "bravo");
        var first = await store.GetSessionAsync(agent, "delta", "bravo:c-charlie");
        var second = await store.GetSessionAsync(agent, "charlie:c-delta", "bravo");

        // Assert
        Assert.Equal("first", Assert.IsType<TestSession>(first).Value);
        Assert.Equal("second", Assert.IsType<TestSession>(second).Value);
    }

    private sealed class TestSession(string value) : AgentSession
    {
        public string Value { get; } = value;
    }

    private sealed class TestAgent(string name) : AIAgent
    {
        public override string? Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            ValueTask.FromResult<AgentSession>(new TestSession(string.Empty));

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            var testSession = Assert.IsType<TestSession>(session);
            return ValueTask.FromResult(JsonSerializer.SerializeToElement(testSession.Value));
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            ValueTask.FromResult<AgentSession>(new TestSession(serializedState.GetString()!));

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<Microsoft.Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
    }
}
