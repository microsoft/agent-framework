// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.UnitTests.Futures;
using Microsoft.Extensions.AI;

#pragma warning disable SYSLIB1045 // Use GeneratedRegex
#pragma warning disable RCS1186 // Use Regex instance instead of static method

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class ConcurrentWorkflowBuilderTests
{
    [Fact]
    public void Test_ConcurrentWorkflowBuilder_InvalidArguments_Throws()
    {
        Assert.Throws<ArgumentNullException>("agents", () => new ConcurrentWorkflowBuilder(null!));
        Assert.Throws<ArgumentException>("agents", () => new ConcurrentWorkflowBuilder().Build());

        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.BuildConcurrent(null!));
        Assert.Throws<ArgumentNullException>("agents", () => AgentWorkflowBuilder.CreateConcurrentBuilderWith(null!));
    }

    [Fact]
    public async Task Test_ConcurrentWorkflowBuilder_AgentsRunInParallelAsync()
    {
        StrongBox<TaskCompletionSource<bool>> barrier = new();
        StrongBox<int> remaining = new();

        var workflow = new ConcurrentWorkflowBuilder(
            new OrchestrationTestHelpers.DoubleEchoAgentWithBarrier("agent1", barrier, remaining),
            new OrchestrationTestHelpers.DoubleEchoAgentWithBarrier("agent2", barrier, remaining))
            .Build();

        for (int iter = 0; iter < 3; iter++)
        {
            barrier.Value = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            remaining.Value = 2;

            (string updateText, List<ChatMessage>? result, _, _) =
                await OrchestrationTestHelpers.RunWorkflowAsync(workflow, [new ChatMessage(ChatRole.User, "abc")]);
            Assert.NotEmpty(updateText);
            Assert.NotNull(result);

            // TODO: https://github.com/microsoft/agent-framework/issues/784
            // These asserts are flaky until we guarantee message delivery order.
            Assert.Single(Regex.Matches(updateText, "agent1"));
            Assert.Single(Regex.Matches(updateText, "agent2"));
            Assert.Equal(4, Regex.Matches(updateText, "abc").Count);
            Assert.Equal(2, result.Count);
        }
    }

    [Fact]
    public void Test_ConcurrentWorkflowBuilder_DefaultDesignationsMatchSpec()
    {
        Workflow workflow = new ConcurrentWorkflowBuilder(
            new OrchestrationTestHelpers.DoubleEchoAgent("agent1"),
            new OrchestrationTestHelpers.DoubleEchoAgent("agent2"),
            new OrchestrationTestHelpers.DoubleEchoAgent("agent3"))
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;
        designations.Where(kvp => kvp.Value.Count == 0)
            .Should().ContainSingle("ConcurrentEndExecutor is the sole terminal output by default");
        designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))
            .Should().HaveCount(6, "every agent (3) and per-agent accumulator (3) is designated intermediate by default");
    }

    [Fact]
    public void Test_ConcurrentWorkflowBuilder_ExplicitDesignationsReplaceDefaults()
    {
        OrchestrationTestHelpers.DoubleEchoAgent a1 = new("agent1");
        OrchestrationTestHelpers.DoubleEchoAgent a2 = new("agent2");
        OrchestrationTestHelpers.DoubleEchoAgent a3 = new("agent3");

        Workflow workflow = new ConcurrentWorkflowBuilder(a1, a2, a3)
            .WithOutputFrom(a1)
            .WithIntermediateOutputFrom([a2])
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Should().HaveCount(2,
            "only the two explicitly-designated agents land on the inner builder; the end + accumulator defaults are suppressed");
        designations.Values.Where(tags => tags.Count == 0)
            .Should().ContainSingle("agent1 is the only terminal designation");
        designations.Values.Where(tags => tags.Contains(OutputTag.Intermediate))
            .Should().ContainSingle("agent2 is the only intermediate designation");
    }

    [Fact]
    public void Test_ConcurrentWorkflowBuilder_DesignationForNonParticipantThrows()
    {
        OrchestrationTestHelpers.DoubleEchoAgent participant = new("p1");
        OrchestrationTestHelpers.DoubleEchoAgent stranger = new("stranger");

        ConcurrentWorkflowBuilder builder = new ConcurrentWorkflowBuilder(participant)
            .WithIntermediateOutputFrom([stranger]);

        Action build = () => builder.Build();
        build.Should().Throw<InvalidOperationException>().WithMessage("*stranger*");
    }

    [Fact]
    public void Test_ConcurrentWorkflowBuilder_WithNamePropagatesToWorkflow()
    {
        Workflow workflow = new ConcurrentWorkflowBuilder(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
            .WithName("named-concurrent")
            .Build();

        workflow.Name.Should().Be("named-concurrent");
    }

    [Fact]
    public void Test_ConcurrentWorkflowBuilder_WithDescriptionPropagatesToWorkflow()
    {
        Workflow workflow = new ConcurrentWorkflowBuilder(new OrchestrationTestHelpers.DoubleEchoAgent("agent1"))
            .WithDescription("describes the concurrent fan-out/fan-in")
            .Build();

        workflow.Description.Should().Be("describes the concurrent fan-out/fan-in");
    }

    [Collection(FuturesSerialCollection.Name)]
    public class AsAgentForwarding
    {
        [Fact]
        public async Task Test_ConcurrentWorkflowBuilder_AsAgent_OnlyTerminalDesignationSurfacesAsync()
        {
            using FuturesScope _ = new(enabled: true);

            OrchestrationTestHelpers.DoubleEchoAgent agent1 = new("agent1");
            OrchestrationTestHelpers.DoubleEchoAgent agent2 = new("agent2");

            // Designate only agent1 as a terminal output source — agent2 and the fan-in
            // aggregator default-intermediate designations are suppressed.
            Workflow workflow = new ConcurrentWorkflowBuilder(agent1, agent2)
                .WithOutputFrom(agent1)
                .Build();

            List<AgentResponseUpdate> updates = await workflow
                .AsAIAgent("WorkflowAgent")
                .RunStreamingAsync(new ChatMessage(ChatRole.User, "abc"))
                .ToListAsync();

            HashSet<string> authoredBy = updates
                .Select(u => u.AuthorName)
                .Where(n => !string.IsNullOrEmpty(n))
                .Select(n => n!)
                .ToHashSet();

            authoredBy.Should().Contain("agent1", "the designated agent must surface");
            authoredBy.Should().NotContain("agent2",
                "the undesignated agent must not surface when only one is designated under Futures-on");
        }
    }
}
