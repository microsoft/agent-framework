// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="FileAgentSkillScriptExecutor"/> and its integration with <see cref="FileAgentSkillsProvider"/>.
/// </summary>
public sealed class FileAgentSkillScriptExecutorTests : IDisposable
{
    private readonly string _testRoot;
    private readonly TestAIAgent _agent = new();
    private static readonly FileAgentSkillScriptExecutionContext s_emptyContext = new(
        new Dictionary<string, FileAgentSkill>(StringComparer.OrdinalIgnoreCase),
        new FileAgentSkillLoader(NullLogger.Instance));

    public FileAgentSkillScriptExecutorTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "skill-executor-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._testRoot);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._testRoot))
        {
            Directory.Delete(this._testRoot, recursive: true);
        }
    }

    [Fact]
    public void HostedCodeInterpreter_ReturnsNonNullInstance()
    {
        // Act
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();

        // Assert
        Assert.NotNull(executor);
    }

    [Fact]
    public void HostedCodeInterpreter_GetExecutionDetails_ReturnsNonNullInstructions()
    {
        // Arrange
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();

        // Act
        var details = executor.GetExecutionDetails(s_emptyContext);

        // Assert
        Assert.NotNull(details);
        Assert.NotNull(details.Instructions);
        Assert.NotEmpty(details.Instructions);
    }

    [Fact]
    public void HostedCodeInterpreter_GetExecutionDetails_ReturnsNonEmptyToolsList()
    {
        // Arrange
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();

        // Act
        var details = executor.GetExecutionDetails(s_emptyContext);

        // Assert
        Assert.NotNull(details);
        Assert.NotNull(details.Tools);
        Assert.NotEmpty(details.Tools);
    }

    [Fact]
    public async Task Provider_WithExecutor_IncludesExecutorInstructionsInPromptAsync()
    {
        // Arrange
        CreateSkill(this._testRoot, "exec-skill", "Executor test", "Body.");
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();
        var options = new FileAgentSkillsProviderOptions { ScriptExecutor = executor };
        var provider = new FileAgentSkillsProvider(this._testRoot, options);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — executor instructions should be merged into the prompt
        Assert.NotNull(result.Instructions);
        Assert.Contains("code interpreter", result.Instructions, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Provider_WithExecutor_IncludesExecutorToolsAsync()
    {
        // Arrange
        CreateSkill(this._testRoot, "tools-exec-skill", "Executor tools test", "Body.");
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();
        var options = new FileAgentSkillsProviderOptions { ScriptExecutor = executor };
        var provider = new FileAgentSkillsProvider(this._testRoot, options);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — should have 3 tools: load_skill, read_skill_resource, and HostedCodeInterpreterTool
        Assert.NotNull(result.Tools);
        Assert.Equal(3, result.Tools!.Count());
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("load_skill", toolNames);
        Assert.Contains("read_skill_resource", toolNames);
        Assert.Single(result.Tools!, t => t is HostedCodeInterpreterTool);
    }

    [Fact]
    public async Task Provider_WithoutExecutor_DoesNotIncludeExecutorToolsAsync()
    {
        // Arrange
        CreateSkill(this._testRoot, "no-exec-skill", "No executor test", "Body.");
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — should only have the two base tools
        Assert.NotNull(result.Tools);
        Assert.Equal(2, result.Tools!.Count());
    }

    [Fact]
    public async Task Provider_WithHostedCodeInterpreter_MergesScriptInstructionsIntoPromptAsync()
    {
        // Arrange
        CreateSkill(this._testRoot, "merge-skill", "Merge test", "Body.");
        var executor = FileAgentSkillScriptExecutor.HostedCodeInterpreter();
        var options = new FileAgentSkillsProviderOptions { ScriptExecutor = executor };
        var provider = new FileAgentSkillsProvider(this._testRoot, options);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — prompt should contain both the skill listing and the executor's script instructions
        Assert.NotNull(result.Instructions);
        string instructions = result.Instructions!;

        // Skill listing is present
        Assert.Contains("merge-skill", instructions);
        Assert.Contains("Merge test", instructions);

        // Hosted code interpreter script instructions are merged into the prompt
        Assert.Contains("executable scripts", instructions);
        Assert.Contains("read_skill_resource", instructions);
        Assert.Contains("Execute the script using the code interpreter", instructions);
    }

    private static void CreateSkill(string root, string name, string description, string body)
    {
        string skillDir = Path.Combine(root, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {name}\ndescription: {description}\n---\n{body}");
    }
}
