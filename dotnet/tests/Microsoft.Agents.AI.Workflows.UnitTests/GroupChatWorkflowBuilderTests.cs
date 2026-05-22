// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class GroupChatWorkflowBuilderTests
{
    [Fact]
    public void BuildGroupChat_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("managerFactory", () => AgentWorkflowBuilder.CreateGroupChatBuilderWith(null!));

        var groupChat = AgentWorkflowBuilder.CreateGroupChatBuilderWith(_ => new RoundRobinGroupChatManager([new AgentWorkflowBuilderTests.DoubleEchoAgent("a1")]));
        Assert.NotNull(groupChat);
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(null!));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants([null!]));
        Assert.Throws<ArgumentNullException>("agents", () => groupChat.AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("a1"), null!));

        Assert.Throws<ArgumentNullException>("agents", () => new RoundRobinGroupChatManager(null!));
    }

    [Fact]
    public void GroupChatManager_MaximumIterationCount_Invalid_Throws()
    {
        var manager = new RoundRobinGroupChatManager([new AgentWorkflowBuilderTests.DoubleEchoAgent("a1")]);

        const int DefaultMaxIterations = 40;
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = 0);
        Assert.Throws<ArgumentOutOfRangeException>("value", void () => manager.MaximumIterationCount = -1);
        Assert.Equal(DefaultMaxIterations, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 30;
        Assert.Equal(30, manager.MaximumIterationCount);

        manager.MaximumIterationCount = 1;
        Assert.Equal(1, manager.MaximumIterationCount);

        manager.MaximumIterationCount = int.MaxValue;
        Assert.Equal(int.MaxValue, manager.MaximumIterationCount);
    }

    [Fact]
    public void BuildGroupChat_WithNameAndDescription_SetsWorkflowNameAndDescription()
    {
        const string WorkflowName = "Test Group Chat";
        const string WorkflowDescription = "A test group chat workflow";

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("agent1"), new AgentWorkflowBuilderTests.DoubleEchoAgent("agent2"))
            .WithName(WorkflowName)
            .WithDescription(WorkflowDescription)
            .Build();

        Assert.Equal(WorkflowName, workflow.Name);
        Assert.Equal(WorkflowDescription, workflow.Description);
    }

    [Fact]
    public void BuildGroupChat_WithNameOnly_SetsWorkflowName()
    {
        const string WorkflowName = "Named Group Chat";

        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("agent1"))
            .WithName(WorkflowName)
            .Build();

        Assert.Equal(WorkflowName, workflow.Name);
        Assert.Null(workflow.Description);
    }

    [Fact]
    public void BuildGroupChat_WithoutNameOrDescription_DefaultsToNull()
    {
        var workflow = AgentWorkflowBuilder
            .CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = 2 })
            .AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("agent1"))
            .Build();

        Assert.Null(workflow.Name);
        Assert.Null(workflow.Description);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    public async Task BuildGroupChat_AgentsRunInOrderAsync(int maxIterations)
    {
        const int NumAgents = 3;
        var workflow = AgentWorkflowBuilder.CreateGroupChatBuilderWith(agents => new RoundRobinGroupChatManager(agents) { MaximumIterationCount = maxIterations })
            .AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("agent1"), new AgentWorkflowBuilderTests.DoubleEchoAgent("agent2"))
            .AddParticipants(new AgentWorkflowBuilderTests.DoubleEchoAgent("agent3"))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            const string UserInput = "abc";
            (string updateText, List<ChatMessage>? result, _, _) = await AgentWorkflowBuilderTests.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, UserInput)]);

            Assert.NotNull(result);
            Assert.Equal(maxIterations + 1, result.Count);

            Assert.Equal(ChatRole.User, result[0].Role);
            Assert.Null(result[0].AuthorName);
            Assert.Equal(UserInput, result[0].Text);

            string[] texts = new string[maxIterations + 1];
            texts[0] = UserInput;
            string expectedTotal = string.Empty;
            for (int i = 1; i < maxIterations + 1; i++)
            {
                string id = $"agent{((i - 1) % NumAgents) + 1}";
                texts[i] = $"{id}{Double(string.Concat(texts.Take(i)))}";
                Assert.Equal(ChatRole.Assistant, result[i].Role);
                Assert.Equal(id, result[i].AuthorName);
                Assert.Equal(texts[i], result[i].Text);
                expectedTotal += texts[i];
            }

            Assert.Equal(expectedTotal, updateText);
            Assert.Equal(UserInput + expectedTotal, string.Concat(result));

            static string Double(string s) => s + s;
        }
    }
}
