// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public sealed class InMemoryAgentSessionStoreTests
{
    [Fact]
    public async Task DeleteSessionAsync_RemovesOnlyTheTargetedSessionAsync()
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();
        var agent = new TestAgent();
        var aliceKey = new AgentSessionStoreKey("shared").WithPartition("user", "alice");
        var bobKey = new AgentSessionStoreKey("shared").WithPartition("user", "bob");
        await store.SaveSessionAsync(agent, aliceKey, new TestSession());
        await store.SaveSessionAsync(agent, bobKey, new TestSession());

        // Act
        await store.DeleteSessionAsync(agent, aliceKey);

        // Assert
        Assert.Null(await store.GetSessionAsync(agent, aliceKey));
        Assert.NotNull(await store.GetSessionAsync(agent, bobKey));
    }

    [Fact]
    public async Task DeleteSessionAsync_MissingSession_DoesNotThrowAsync()
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();
        var agent = new TestAgent();

        // Act
        await store.DeleteSessionAsync(agent, new AgentSessionStoreKey("missing"));

        // Assert
        Assert.Null(await store.GetSessionAsync(agent, new AgentSessionStoreKey("missing")));
    }

    private sealed class TestSession : AgentSession;

    private sealed class TestAgent : AIAgent
    {
        public override string? Name => "test-agent";

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => new(new TestSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            using var document = JsonDocument.Parse("{}");
            return new(document.RootElement.Clone());
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
            => new(new TestSession());

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
