// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class RoundRobinGroupChatManagerTests
{
    [Fact]
    public async Task RoundRobinGroupChat_SelectNextAgent_CyclesInOrderAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        TestEchoAgent agent2 = new(id: "agent2");
        TestEchoAgent agent3 = new(id: "agent3");
        List<AIAgent> agents = [agent1, agent2, agent3];
        List<ChatMessage> history = [];

        RoundRobinGroupChatManager manager = new(agents);

        AIAgent first = await manager.SelectNextAgentAsync(history);
        AIAgent second = await manager.SelectNextAgentAsync(history);
        AIAgent third = await manager.SelectNextAgentAsync(history);

        Assert.Same(agent1, first);
        Assert.Same(agent2, second);
        Assert.Same(agent3, third);
    }

    [Fact]
    public async Task RoundRobinGroupChat_SelectNextAgent_WrapsAroundAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        TestEchoAgent agent2 = new(id: "agent2");
        List<AIAgent> agents = [agent1, agent2];
        List<ChatMessage> history = [];

        RoundRobinGroupChatManager manager = new(agents);

        await manager.SelectNextAgentAsync(history);
        await manager.SelectNextAgentAsync(history);

        AIAgent wrappedAgent = await manager.SelectNextAgentAsync(history);

        Assert.Same(agent1, wrappedAgent);
    }

    [Fact]
    public async Task RoundRobinGroupChat_ShouldTerminate_DefaultBehaviorTerminatesAtMaxIterationsAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        List<AIAgent> agents = [agent1];
        List<ChatMessage> history = [];

        RoundRobinGroupChatManager manager = new(agents) { MaximumIterationCount = 3 };

        manager.IterationCount = 2;
        bool shouldTerminateBefore = await manager.ShouldTerminateAsync(history);
        Assert.False(shouldTerminateBefore);

        manager.IterationCount = 3;
        bool shouldTerminateAt = await manager.ShouldTerminateAsync(history);
        Assert.True(shouldTerminateAt);
    }

    [Fact]
    public async Task RoundRobinGroupChat_ShouldTerminate_CustomFuncTerminatesEarlyAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        List<AIAgent> agents = [agent1];
        List<ChatMessage> history = [new ChatMessage(ChatRole.Assistant, "done")];

        RoundRobinGroupChatManager manager = new(agents,
            shouldTerminateFunc: (_, messages, _) => new(messages.Any(m => m.Text == "done")))
        {
            MaximumIterationCount = 100
        };

        bool shouldTerminate = await manager.ShouldTerminateAsync(history);
        Assert.True(shouldTerminate);
    }

    [Fact]
    public async Task RoundRobinGroupChat_ShouldTerminate_CustomFuncDoesNotTerminateWhenNotMetAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        List<AIAgent> agents = [agent1];
        List<ChatMessage> history = [new ChatMessage(ChatRole.Assistant, "continue")];

        RoundRobinGroupChatManager manager = new(agents,
            shouldTerminateFunc: (_, messages, _) => new(messages.Any(m => m.Text == "done")))
        {
            MaximumIterationCount = 100
        };

        bool shouldTerminate = await manager.ShouldTerminateAsync(history);
        Assert.False(shouldTerminate);
    }

    [Fact]
    public async Task RoundRobinGroupChat_Reset_ResetsIterationCountAndAgentIndexAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        TestEchoAgent agent2 = new(id: "agent2");
        List<AIAgent> agents = [agent1, agent2];
        List<ChatMessage> history = [];

        RoundRobinGroupChatManager manager = new(agents);
        manager.IterationCount = 5;

        // Advance the internal index past the first agent
        await manager.SelectNextAgentAsync(history);

        manager.Reset();

        Assert.Equal(0, manager.IterationCount);

        AIAgent afterReset = await manager.SelectNextAgentAsync(history);
        Assert.Same(agent1, afterReset);
    }

    [Fact]
    public void RoundRobinGroupChat_Constructor_ThrowsOnNullAgents()
    {
        Assert.Equal("agents", Assert.Throws<System.ArgumentNullException>(() => new RoundRobinGroupChatManager(null!)).ParamName);
    }

    [Fact]
    public void RoundRobinGroupChat_Constructor_ThrowsOnEmptyAgents()
    {
        Assert.Throws<System.ArgumentException>(() => new RoundRobinGroupChatManager([]));
    }

    [Fact]
    public async Task RoundRobinGroupChat_CheckpointRoundTrip_PreservesIterationCountAndCursorAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        TestEchoAgent agent2 = new(id: "agent2");
        TestEchoAgent agent3 = new(id: "agent3");
        List<AIAgent> agents = [agent1, agent2, agent3];
        List<ChatMessage> history = [];

        TestRunState sharedState = new();
        TestWorkflowContext sourceContext = new("gcm-host", sharedState);
        TestWorkflowContext sinkContext = new("gcm-host", sharedState);

        RoundRobinGroupChatManager source = new(agents);
        await source.SelectNextAgentAsync(history); // cursor -> agent2
        source.IterationCount = 7;

        await source.CheckpointAsync(sourceContext);

        RoundRobinGroupChatManager restored = new(agents);
        Assert.Equal(0, restored.IterationCount);

        await restored.RestoreCheckpointAsync(sinkContext);

        Assert.Equal(7, restored.IterationCount);

        AIAgent next = await restored.SelectNextAgentAsync(history);
        Assert.Same(agent2, next);
    }

    [Fact]
    public async Task RoundRobinGroupChat_RestoreWithoutCheckpoint_DefaultsToZeroStateAsync()
    {
        TestEchoAgent agent1 = new(id: "agent1");
        TestEchoAgent agent2 = new(id: "agent2");
        List<AIAgent> agents = [agent1, agent2];
        List<ChatMessage> history = [];

        TestWorkflowContext emptyContext = new("gcm-host");

        RoundRobinGroupChatManager manager = new(agents);
        manager.IterationCount = 3;
        await manager.SelectNextAgentAsync(history); // cursor advanced

        await manager.RestoreCheckpointAsync(emptyContext);

        Assert.Equal(0, manager.IterationCount);
        AIAgent next = await manager.SelectNextAgentAsync(history);
        Assert.Same(agent1, next);
    }
}
