// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

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

        Assert.Single(designations, kvp => kvp.Value.Count == 0);
        Assert.Equal(2, designations.Where(kvp => kvp.Value.Contains(OutputTag.Intermediate))?.Count());
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

        Assert.Equal(2, designations.Count);
        Assert.Single(designations.Values, tags => tags.Count == 0);
        Assert.Single(designations.Values, tags => tags.Contains(OutputTag.Intermediate));
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

        void build() => builder.Build();
        Assert.Contains("Stranger", Assert.Throws<InvalidOperationException>(build).Message);
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
        Assert.Same(builder, chained);
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
        Assert.Same(builder, chained);
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
        void build() => builder.Build();

        // Assert
        Assert.Contains("{schema}", Assert.Throws<InvalidOperationException>(build).Message);
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
        void build() => builder.Build();

        // Assert
        Assert.Null(Record.Exception(build));
    }
}
#pragma warning restore MAAIW001
