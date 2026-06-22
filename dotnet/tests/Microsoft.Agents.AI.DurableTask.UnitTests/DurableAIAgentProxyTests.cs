// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.UnitTests;

public sealed class DurableAIAgentProxyTests
{
    // Verifies the proxy rejects a session whose agent name differs from its own,
    // and that the durable client is never called when this happens.
    [Fact]
    public async Task RunAsync_ThrowsWhenSessionBelongsToDifferentAgentAsync()
    {
        StubDurableAgentClient client = new();
        DurableAIAgentProxy proxy = new("agentA", client);
        DurableAgentSession session = new(new AgentSessionId("agentB", "shared-key"));

        ArgumentException ex = await Assert.ThrowsAsync<ArgumentException>(() =>
            proxy.RunAsync(new ChatMessage(ChatRole.User, "hello"), session));

        Assert.Equal("session", ex.ParamName);
        Assert.Contains("agentB", ex.Message, StringComparison.Ordinal);
        Assert.Contains("agentA", ex.Message, StringComparison.Ordinal);
        Assert.Equal(0, client.CallCount);
    }

    // Control test: when the session's agent name matches the proxy's name,
    // the request is forwarded to the durable client.
    [Fact]
    public async Task RunAsync_AllowsSessionWhenAgentNameMatchesAsync()
    {
        AgentSessionId sessionId = new("agentA", "shared-key");
        InvalidOperationException sentinel = new("reached the client");
        StubDurableAgentClient client = new() { Throw = sentinel };
        DurableAIAgentProxy proxy = new("agentA", client);
        DurableAgentSession session = new(sessionId);

        // Reaching the durable client (and therefore propagating the sentinel) proves the
        // name-matching guard accepted this session.
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            proxy.RunAsync(new ChatMessage(ChatRole.User, "hello"), session));

        Assert.Same(sentinel, ex);
        Assert.Equal(1, client.CallCount);
        Assert.Equal(sessionId, client.LastSessionId);
    }

    // Ensures the agent-name comparison is case-insensitive, so casing differences
    // are neither a false-positive rejection nor a bypass.
    [Fact]
    public async Task RunAsync_AgentNameComparisonIsCaseInsensitiveAsync()
    {
        AgentSessionId sessionId = new("AGENTA", "shared-key");
        InvalidOperationException sentinel = new("reached the client");
        StubDurableAgentClient client = new() { Throw = sentinel };
        DurableAIAgentProxy proxy = new("agentA", client);
        DurableAgentSession session = new(sessionId);

        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            proxy.RunAsync(new ChatMessage(ChatRole.User, "hello"), session));

        Assert.Same(sentinel, ex);
        Assert.Equal(1, client.CallCount);
    }

    private sealed class StubDurableAgentClient : IDurableAgentClient
    {
        public int CallCount { get; private set; }
        public AgentSessionId LastSessionId { get; private set; }
        public Exception? Throw { get; set; }

        public Task<AgentRunHandle> RunAgentAsync(
            AgentSessionId sessionId,
            RunRequest request,
            CancellationToken cancellationToken)
        {
            this.CallCount++;
            this.LastSessionId = sessionId;
            if (this.Throw is not null)
            {
                return Task.FromException<AgentRunHandle>(this.Throw);
            }

            throw new InvalidOperationException("Test did not configure a response.");
        }
    }
}
