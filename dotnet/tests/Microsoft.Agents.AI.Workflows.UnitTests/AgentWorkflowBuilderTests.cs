// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests targeting the static <see cref="AgentWorkflowBuilder"/> helper surface —
/// <see cref="AgentWorkflowBuilder.BuildSequential(IEnumerable{AIAgent})"/>,
/// <see cref="AgentWorkflowBuilder.BuildConcurrent(IEnumerable{AIAgent}, Func{IList{List{ChatMessage}}, List{ChatMessage}})"/>,
/// and the various <c>Create*BuilderWith</c> factories. Per-builder unit tests live in their own
/// files (<see cref="SequentialWorkflowBuilderTests"/>, <see cref="ConcurrentWorkflowBuilderTests"/>, etc.).
/// </summary>
public class AgentWorkflowBuilderTests
{
    [Fact]
    public void Test_AgentWorkflowBuilder_BuildSequential_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildSequential(workflowName: null!, null!));
        Assert.Throws<ArgumentException>("agents", () => AgentWorkflowBuilder.BuildSequential());
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    public async Task Test_AgentWorkflowBuilder_BuildSequential_DelegatesToBuilderAsync(int numAgents)
    {
        Workflow workflow = AgentWorkflowBuilder.BuildSequential(
            from i in Enumerable.Range(1, numAgents)
            select new OrchestrationTestHelpers.DoubleEchoAgent($"agent{i}"));

        // Smoke: end-to-end run produces a non-empty result. Detailed pipeline-ordering
        // assertions live in SequentialWorkflowBuilderTests.
        (string updateText, List<ChatMessage>? result, _, _) =
            await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.NotNull(result);
        Assert.Equal(numAgents + 1, result.Count);
        Assert.NotEmpty(updateText);
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_BuildSequential_WithWorkflowNameSetsNameOnWorkflow()
    {
        Workflow workflow = AgentWorkflowBuilder.BuildSequential(
            "static-sequential",
            new OrchestrationTestHelpers.DoubleEchoAgent("agent1"));

        workflow.Name.Should().Be("static-sequential");
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_BuildConcurrent_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildConcurrent(null!));
    }

    [Fact]
    public async Task Test_AgentWorkflowBuilder_BuildConcurrent_DelegatesToBuilderAsync()
    {
        StrongBox<TaskCompletionSource<bool>> barrier = new();
        StrongBox<int> remaining = new();

        Workflow workflow = AgentWorkflowBuilder.BuildConcurrent(
        [
            new OrchestrationTestHelpers.DoubleEchoAgentWithBarrier("agent1", barrier, remaining),
            new OrchestrationTestHelpers.DoubleEchoAgentWithBarrier("agent2", barrier, remaining),
        ]);

        barrier.Value = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        remaining.Value = 2;

        (string updateText, List<ChatMessage>? result, _, _) =
            await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        Assert.NotEmpty(updateText);
        Assert.NotNull(result);
        Assert.Equal(2, result.Count);
        Assert.Single(Regex.Matches(updateText, "agent1"));
        Assert.Single(Regex.Matches(updateText, "agent2"));
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_BuildConcurrent_WithWorkflowNameSetsNameOnWorkflow()
    {
        Workflow workflow = AgentWorkflowBuilder.BuildConcurrent(
            "static-concurrent",
            [new OrchestrationTestHelpers.DoubleEchoAgent("agent1")]);

        workflow.Name.Should().Be("static-concurrent");
    }

    [Fact]
    public async Task Test_AgentWorkflowBuilder_BuildConcurrent_AggregatorIsHonoredAsync()
    {
        // Replace the default ("last message from each agent") with a custom aggregator,
        // and confirm the workflow yields its result.
        List<ChatMessage> sentinel = [new(ChatRole.Assistant, "custom-aggregator-result")];

        Workflow workflow = AgentWorkflowBuilder.BuildConcurrent(
            [new OrchestrationTestHelpers.DoubleEchoAgent("agent1")],
            aggregator: _ => sentinel);

        (_, List<ChatMessage>? result, _, _) =
            await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);

        result.Should().NotBeNull().And.ContainSingle();
        result![0].Text.Should().Be("custom-aggregator-result");
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateSequentialBuilderWith_RejectsNull()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.CreateSequentialBuilderWith(null!));
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateSequentialBuilderWith_ReturnsConfigurableBuilder()
    {
        OrchestrationTestHelpers.DoubleEchoAgent agent = new("agent1");

        SequentialWorkflowBuilder builder = AgentWorkflowBuilder.CreateSequentialBuilderWith(agent);
        Workflow workflow = builder.WithName("via-factory").Build();

        workflow.Name.Should().Be("via-factory");
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateConcurrentBuilderWith_RejectsNull()
    {
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.CreateConcurrentBuilderWith(null!));
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateConcurrentBuilderWith_ReturnsConfigurableBuilder()
    {
        OrchestrationTestHelpers.DoubleEchoAgent agent = new("agent1");

        ConcurrentWorkflowBuilder builder = AgentWorkflowBuilder.CreateConcurrentBuilderWith(agent);
        Workflow workflow = builder.WithName("via-factory").Build();

        workflow.Name.Should().Be("via-factory");
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateHandoffBuilderWith_RejectsNull()
    {
#pragma warning disable MAAIW001
        Assert.Throws<ArgumentNullException>("initialAgent", () => AgentWorkflowBuilder.CreateHandoffBuilderWith(null!));
#pragma warning restore MAAIW001
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateGroupChatBuilderWith_RejectsNull()
    {
        Assert.Throws<ArgumentNullException>("managerFactory", () => AgentWorkflowBuilder.CreateGroupChatBuilderWith(null!));
    }

    [Fact]
    public void Test_AgentWorkflowBuilder_CreateMagenticBuilderWith_RejectsNull()
    {
#pragma warning disable MAAIW001
        Assert.Throws<ArgumentNullException>("managerAgent", () => AgentWorkflowBuilder.CreateMagenticBuilderWith(null!));
#pragma warning restore MAAIW001
    }
}
