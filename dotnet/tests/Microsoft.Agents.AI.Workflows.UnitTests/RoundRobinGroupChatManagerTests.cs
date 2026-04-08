// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
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

        first.Should().BeSameAs(agent1);
        second.Should().BeSameAs(agent2);
        third.Should().BeSameAs(agent3);
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

        wrappedAgent.Should().BeSameAs(agent1, "the manager should wrap around to the first agent after cycling through all agents");
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
        shouldTerminateBefore.Should().BeFalse("the iteration count has not yet reached the maximum");

        manager.IterationCount = 3;
        bool shouldTerminateAt = await manager.ShouldTerminateAsync(history);
        shouldTerminateAt.Should().BeTrue("the iteration count has reached the maximum");
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
        shouldTerminate.Should().BeTrue("the custom termination function should cause early termination");
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
        shouldTerminate.Should().BeFalse("the custom termination function should not cause termination when condition is not met");
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

        manager.IterationCount.Should().Be(0, "Reset should clear the iteration count");

        AIAgent afterReset = await manager.SelectNextAgentAsync(history);
        afterReset.Should().BeSameAs(agent1, "Reset should cause the next selection to start from the first agent");
    }

    [Fact]
    public void RoundRobinGroupChat_Constructor_ThrowsOnNullAgents()
    {
        FluentActions.Invoking(() => new RoundRobinGroupChatManager(null!))
            .Should().Throw<System.ArgumentNullException>()
            .WithParameterName("agents");
    }

    [Fact]
    public void RoundRobinGroupChat_Constructor_ThrowsOnEmptyAgents()
    {
        FluentActions.Invoking(() => new RoundRobinGroupChatManager([]))
            .Should().Throw<System.ArgumentException>();
    }
}
