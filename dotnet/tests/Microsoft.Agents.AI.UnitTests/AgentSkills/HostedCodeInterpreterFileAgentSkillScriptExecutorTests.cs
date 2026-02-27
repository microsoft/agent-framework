// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="HostedCodeInterpreterFileAgentSkillScriptExecutor"/>.
/// </summary>
public sealed class HostedCodeInterpreterFileAgentSkillScriptExecutorTests
{
    private static readonly FileAgentSkillScriptExecutionContext s_emptyContext = new(
        new Dictionary<string, FileAgentSkill>(StringComparer.OrdinalIgnoreCase),
        new FileAgentSkillLoader(NullLogger.Instance));

    [Fact]
    public void GetExecutionDetails_ReturnsScriptExecutionGuidance()
    {
        // Arrange
        var executor = new HostedCodeInterpreterFileAgentSkillScriptExecutor();

        // Act
        var details = executor.GetExecutionDetails(s_emptyContext);

        // Assert
        Assert.NotNull(details.Instructions);
        Assert.Contains("read_skill_resource", details.Instructions);
        Assert.Contains("code interpreter", details.Instructions);
    }

    [Fact]
    public void GetExecutionDetails_ReturnsSingleHostedCodeInterpreterTool()
    {
        // Arrange
        var executor = new HostedCodeInterpreterFileAgentSkillScriptExecutor();

        // Act
        var details = executor.GetExecutionDetails(s_emptyContext);

        // Assert
        Assert.NotNull(details.Tools);
        Assert.Single(details.Tools!);
        Assert.IsType<HostedCodeInterpreterTool>(details.Tools![0]);
    }

    [Fact]
    public void GetExecutionDetails_ReturnsSameInstanceOnMultipleCalls()
    {
        // Arrange
        var executor = new HostedCodeInterpreterFileAgentSkillScriptExecutor();

        // Act
        var details1 = executor.GetExecutionDetails(s_emptyContext);
        var details2 = executor.GetExecutionDetails(s_emptyContext);

        // Assert — static details should be reused
        Assert.Same(details1, details2);
    }

    [Fact]
    public void FactoryMethod_ReturnsHostedCodeInterpreterFileAgentSkillScriptExecutor()
    {
        // Act
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();

        // Assert
        Assert.IsType<HostedCodeInterpreterFileAgentSkillScriptExecutor>(executor);
    }
}
