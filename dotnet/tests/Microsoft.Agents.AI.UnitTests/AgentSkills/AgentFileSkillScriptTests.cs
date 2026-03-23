// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentFileSkillScript"/>.
/// </summary>
public sealed class AgentFileSkillScriptTests
{
    [Fact]
    public async Task ExecuteAsync_SkillIsNotAgentFileSkill_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        static Task<object?> ExecutorAsync(AgentFileSkill s, AgentFileSkillScript sc, AIFunctionArguments a, CancellationToken ct) => Task.FromResult<object?>("result");
        var script = CreateScript("test-script", "/path/to/script.py", ExecutorAsync);
        var nonFileSkill = new TestAgentSkill("my-skill", "A skill", "Instructions.");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.ExecuteAsync(nonFileSkill, new AIFunctionArguments(), CancellationToken.None));
    }

    [Fact]
    public async Task ExecuteAsync_WithAgentFileSkill_DelegatesToExecutorAsync()
    {
        // Arrange
        var executorCalled = false;
        Task<object?> executorAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, AIFunctionArguments args, CancellationToken ct)
        {
            executorCalled = true;
            return Task.FromResult<object?>("executed");
        }
        var script = CreateScript("run-me", "/scripts/run-me.sh", executorAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A file skill"),
            "---\nname: my-skill\n---\nContent",
            "/skills/my-skill");

        // Act
        var result = await script.ExecuteAsync(fileSkill, new AIFunctionArguments(), CancellationToken.None);

        // Assert
        Assert.True(executorCalled);
        Assert.Equal("executed", result);
    }

    [Fact]
    public async Task ExecuteAsync_ExecutorReceivesCorrectArgumentsAsync()
    {
        // Arrange
        AgentFileSkill? capturedSkill = null;
        AgentFileSkillScript? capturedScript = null;
        Task<object?> executorAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, AIFunctionArguments args, CancellationToken ct)
        {
            capturedSkill = skill;
            capturedScript = scriptArg;
            return Task.FromResult<object?>(null);
        }
        var script = CreateScript("capture", "/scripts/capture.py", executorAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("owner-skill", "Owner"),
            "Content",
            "/skills/owner-skill");

        // Act
        await script.ExecuteAsync(fileSkill, new AIFunctionArguments(), CancellationToken.None);

        // Assert
        Assert.Same(fileSkill, capturedSkill);
        Assert.Same(script, capturedScript);
    }

    [Fact]
    public void Script_HasCorrectNameAndPath()
    {
        // Arrange & Act
        static Task<object?> ExecutorAsync(AgentFileSkill s, AgentFileSkillScript sc, AIFunctionArguments a, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = CreateScript("my-script", "/path/to/my-script.py", ExecutorAsync);

        // Assert
        Assert.Equal("my-script", script.Name);
        Assert.Equal("/path/to/my-script.py", script.FullPath);
    }

    /// <summary>
    /// Helper to create an <see cref="AgentFileSkillScript"/> via reflection since the constructor is internal.
    /// </summary>
    private static AgentFileSkillScript CreateScript(string name, string fullPath, AgentFileSkillScriptExecutor executor)
    {
        var ctor = typeof(AgentFileSkillScript).GetConstructor(
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance,
            null,
            [typeof(string), typeof(string), typeof(AgentFileSkillScriptExecutor)],
            null) ?? throw new InvalidOperationException("Could not find internal constructor.");

        return (AgentFileSkillScript)ctor.Invoke([name, fullPath, executor]);
    }
}
