// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests focused on <see cref="MagenticWorkflowBuilder"/>'s output-designation surface —
/// the Python-aligned defaults applied at <see cref="MagenticWorkflowBuilder.Build"/> when
/// the user has not made explicit designations, and the memoized
/// <c>WithOutputFrom</c> / <c>WithIntermediateOutputFrom</c> replay otherwise.
/// </summary>
#pragma warning disable MAAIW001 // Experimental: MagenticWorkflowBuilder
public class MagenticWorkflowBuilderTests
{
    [Fact]
    public void Test_MagenticWorkflowBuilder_DefaultDesignationsMatchSpec()
    {
        TestReplayAgent manager = new(name: "Manager");
        TestEchoAgent member1 = new(name: "Worker1");
        TestEchoAgent member2 = new(name: "Worker2");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(member1, member2)
            .RequirePlanSignoff(false)
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Where(kvp => kvp.Value.Count == 0)
            .Should().ContainSingle("the Magentic orchestrator is the sole terminal output by default");
        designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))
            .Should().HaveCount(2, "every team member is designated intermediate by default");
    }

    [Fact]
    public void Test_MagenticWorkflowBuilder_ExplicitDesignationsReplaceDefaults()
    {
        TestReplayAgent manager = new(name: "Manager");
        TestEchoAgent member1 = new(name: "Worker1");
        TestEchoAgent member2 = new(name: "Worker2");

        Workflow workflow = new MagenticWorkflowBuilder(manager)
            .AddParticipants(member1, member2)
            .RequirePlanSignoff(false)
            .WithOutputFrom(member1)
            .WithIntermediateOutputFrom([member2])
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Should().HaveCount(2,
            "only the user-specified designations land on the inner builder; the orchestrator default is suppressed");
        designations.Values.Where(tags => tags.Count == 0)
            .Should().ContainSingle("member1 is the only terminal designation");
        designations.Values.Where(tags => tags.Contains(OutputTag.Intermediate))
            .Should().ContainSingle("member2 is the only intermediate designation");
    }

    [Fact]
    public void Test_MagenticWorkflowBuilder_DesignationForNonParticipantThrows()
    {
        TestReplayAgent manager = new(name: "Manager");
        TestEchoAgent member = new(name: "Worker");
        TestEchoAgent stranger = new(name: "Stranger");

        MagenticWorkflowBuilder builder = new MagenticWorkflowBuilder(manager)
            .AddParticipants(member)
            .RequirePlanSignoff(false)
            .WithIntermediateOutputFrom([stranger]);

        Action build = () => builder.Build();
        build.Should().Throw<InvalidOperationException>().WithMessage("*Stranger*");
    }
}
#pragma warning restore MAAIW001
