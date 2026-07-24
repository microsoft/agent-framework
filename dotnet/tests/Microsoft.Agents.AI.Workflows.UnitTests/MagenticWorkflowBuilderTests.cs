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

    [Fact]
    public void Test_MagenticWorkflowBuilder_WithResponseLanguage_ReturnsSameBuilderForChaining()
    {
        // Arrange
        TestReplayAgent manager = new(name: "Manager");
        MagenticWorkflowBuilder builder = new(manager);

        // Act
        MagenticWorkflowBuilder chained = builder.WithResponseLanguage("English");

        // Assert
        chained.Should().BeSameAs(builder);
    }

    [Fact]
    public void Test_MagenticWorkflowBuilder_WithPromptOverrides_ReturnsSameBuilderForChaining()
    {
        // Arrange
        TestReplayAgent manager = new(name: "Manager");
        MagenticWorkflowBuilder builder = new(manager);

        // Act
        MagenticWorkflowBuilder chained = builder.WithPromptOverrides(new MagenticPromptOverrides { FinalAnswerPrompt = "custom {task}" });

        // Assert
        chained.Should().BeSameAs(builder);
    }

    [Fact]
    public void Test_MagenticWorkflowBuilder_ProgressLedgerOverrideWithoutSchema_ThrowsOnBuild()
    {
        // Arrange
        TestReplayAgent manager = new(name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        MagenticWorkflowBuilder builder = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithPromptOverrides(new MagenticPromptOverrides { ProgressLedgerPrompt = "Answer for {task} with no schema placeholder" });

        // Act
        Action build = () => builder.Build();

        // Assert
        build.Should().Throw<InvalidOperationException>().WithMessage("*{schema}*");
    }

    [Fact]
    public void Test_MagenticWorkflowBuilder_ProgressLedgerOverrideWithSchema_BuildsSuccessfully()
    {
        // Arrange
        TestReplayAgent manager = new(name: "Manager");
        TestEchoAgent worker = new(name: "Worker");

        MagenticWorkflowBuilder builder = new MagenticWorkflowBuilder(manager)
            .AddParticipants(worker)
            .RequirePlanSignoff(false)
            .WithPromptOverrides(new MagenticPromptOverrides { ProgressLedgerPrompt = "Answer for {task}\n{schema}" });

        // Act
        Action build = () => builder.Build();

        // Assert
        build.Should().NotThrow();
    }
}
#pragma warning restore MAAIW001
