// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class InMemoryAgentSessionStoreTests
{
    [Fact]
    public async Task GetSessionAsync_SameNameAcrossAgentInstances_RestoresIndependentSessionsAsync()
    {
        // Arrange
        AIAgent first = new ChatClientAgent(new Mock<IChatClient>().Object, name: "assistant");
        AIAgent second = new ChatClientAgent(new Mock<IChatClient>().Object, name: "assistant");
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        AgentSession original = await first.CreateSessionAsync();
        original.StateBag.SetValue("marker", "saved");
        await store.SaveSessionAsync(first, key, original);

        // Act
        AgentSession? restored = await store.GetSessionAsync(second, key);
        Assert.NotNull(restored);
        restored.StateBag.SetValue("marker", "changed");
        AgentSession? again = await store.GetSessionAsync(first, key);

        // Assert
        Assert.NotEqual(first.Id, second.Id);
        Assert.NotNull(again);
        Assert.NotSame(restored, again);
        Assert.Equal("saved", again.StateBag.GetValue<string>("marker"));
    }

    [Fact]
    public async Task GetSessionAsync_UnnamedAgents_UseInstanceIdentityAsync()
    {
        // Arrange
        AIAgent first = new ChatClientAgent(new Mock<IChatClient>().Object);
        AIAgent second = new ChatClientAgent(new Mock<IChatClient>().Object);
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session");
        await store.SaveSessionAsync(first, key, await first.CreateSessionAsync());

        // Act and assert
        Assert.NotNull(await store.GetSessionAsync(first, key));
        Assert.Null(await store.GetSessionAsync(second, key));
    }

    [Fact]
    public async Task GetSessionAsync_HostingIdentityAndPartitions_IsolateSessionsAsync()
    {
        // Arrange: distinct registrations of the same underlying agent must not share state.
        AIAgent agent = new ChatClientAgent(new Mock<IChatClient>().Object, name: "assistant");
        var first = new FoundryHostingAgent(agent, "key:first");
        var second = new FoundryHostingAgent(agent, "key:second");
        var recreated = new FoundryHostingAgent(new ChatClientAgent(new Mock<IChatClient>().Object), "key:first");
        var store = new InMemoryAgentSessionStore();
        var key = new AgentSessionStoreKey("session").WithPartition("user", "alice").WithPartition("tenant", "one");
        await store.SaveSessionAsync(first, key, await first.CreateSessionAsync());

        // Act and assert
        Assert.NotNull(await store.GetSessionAsync(recreated, key));
        Assert.Null(await store.GetSessionAsync(second, key));
        Assert.Null(await store.GetSessionAsync(first, key.WithPartition("tenant", "two")));
        Assert.Null(await store.GetSessionAsync(first, new AgentSessionStoreKey("session")));
    }
}
