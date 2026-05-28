// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// Tests focused on <see cref="HandoffWorkflowBuilder"/>'s output-designation surface —
/// the Python-aligned defaults applied at <see cref="HandoffWorkflowBuilderCore{TBuilder}.Build"/>
/// when the user has not made explicit designations, and the memoized
/// <c>WithOutputFrom</c> / <c>WithIntermediateOutputFrom</c> replay otherwise.
/// </summary>
#pragma warning disable MAAIW001 // Experimental: HandoffWorkflowBuilder
public class HandoffWorkflowBuilderTests
{
    [Fact]
    public void Test_HandoffWorkflowBuilder_DefaultDesignationsMatchSpec()
    {
        OrchestrationTestHelpers.DoubleEchoAgent coordinator = new("coordinator");
        OrchestrationTestHelpers.DoubleEchoAgent specialist = new("specialist");

        Workflow workflow = AgentWorkflowBuilder
            .CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Where(kvp => kvp.Value.Count == 0)
            .Should().ContainSingle("the handoff end executor is the sole terminal output by default");
        designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))
            .Should().HaveCount(2, "both the coordinator and the specialist are designated intermediate by default");
    }

    [Fact]
    public void Test_HandoffWorkflowBuilder_ExplicitDesignationsReplaceDefaults()
    {
        OrchestrationTestHelpers.DoubleEchoAgent coordinator = new("coordinator");
        OrchestrationTestHelpers.DoubleEchoAgent specialist = new("specialist");

        Workflow workflow = AgentWorkflowBuilder
            .CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .WithOutputFrom(coordinator)
            .WithIntermediateOutputFrom([specialist])
            .Build();

        Dictionary<string, HashSet<OutputTag>> designations = workflow.OutputExecutors;

        designations.Should().HaveCount(2,
            "only the user-specified designations land on the inner builder; the handoff-end default is suppressed");
        designations.Values.Where(tags => tags.Count == 0)
            .Should().ContainSingle("coordinator is the only terminal designation");
        designations.Values.Where(tags => tags.Contains(OutputTag.Intermediate))
            .Should().ContainSingle("specialist is the only intermediate designation");
    }

    [Fact]
    public void Test_HandoffWorkflowBuilder_DesignationForNonParticipantThrows()
    {
        OrchestrationTestHelpers.DoubleEchoAgent coordinator = new("coordinator");
        OrchestrationTestHelpers.DoubleEchoAgent specialist = new("specialist");
        OrchestrationTestHelpers.DoubleEchoAgent stranger = new("stranger");

        HandoffWorkflowBuilder builder = AgentWorkflowBuilder
            .CreateHandoffBuilderWith(coordinator)
            .WithHandoff(coordinator, specialist)
            .WithIntermediateOutputFrom([stranger]);

        Action build = () => builder.Build();
        build.Should().Throw<InvalidOperationException>().WithMessage("*stranger*");
    }
}
#pragma warning restore MAAIW001
