// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for the <see cref="FileAgentSkillsProvider"/> class.
/// </summary>
public sealed class FileAgentSkillsProviderTests : IDisposable
{
    private readonly string _testRoot;
    private readonly TestAIAgent _agent = new();

    public FileAgentSkillsProviderTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "skills-provider-tests-" + Guid.NewGuid().ToString("N"));
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
    public async Task InvokingCoreAsync_NoSkills_ReturnsInputContextUnchangedAsync()
    {
        // Arrange
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var inputContext = new AIContext { Instructions = "Original instructions" };
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.Equal("Original instructions", result.Instructions);
        Assert.Null(result.Tools);
    }

    [Fact]
    public async Task InvokingCoreAsync_WithSkills_AppendsInstructionsAndToolsAsync()
    {
        // Arrange
        this.CreateSkill("provider-skill", "Provider skill test", "Skill instructions body.");
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var inputContext = new AIContext { Instructions = "Base instructions" };
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("Base instructions", result.Instructions);
        Assert.Contains("provider-skill", result.Instructions);
        Assert.Contains("Provider skill test", result.Instructions);

        // Should have load_skill and read_skill_resource tools
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("load_skill", toolNames);
        Assert.Contains("read_skill_resource", toolNames);
    }

    [Fact]
    public async Task InvokingCoreAsync_NullInputInstructions_SetsInstructionsAsync()
    {
        // Arrange
        this.CreateSkill("null-instr-skill", "Null instruction test", "Body.");
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("null-instr-skill", result.Instructions);
    }

    [Fact]
    public async Task InvokingCoreAsync_CustomPromptTemplate_UsesCustomTemplateAsync()
    {
        // Arrange
        this.CreateSkill("custom-prompt-skill", "Custom prompt", "Body.");
        var options = new FileAgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Custom template: {0}"
        };
        var provider = new FileAgentSkillsProvider(this._testRoot, options);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.StartsWith("Custom template:", result.Instructions);
    }

    [Fact]
    public void Constructor_InvalidPromptTemplate_ThrowsArgumentException()
    {
        // Arrange — template with unescaped braces and no valid {0} placeholder
        var options = new FileAgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Bad template with {unescaped} braces"
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() => new FileAgentSkillsProvider(this._testRoot, options));
        Assert.Contains("SkillsInstructionPrompt", ex.Message);
        Assert.Equal("options", ex.ParamName);
    }

    [Fact]
    public async Task InvokingCoreAsync_SkillNamesAreXmlEscapedAsync()
    {
        // Arrange — description with XML-sensitive characters
        string skillDir = Path.Combine(this._testRoot, "xml-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: xml-skill\ndescription: Uses <tags> & \"quotes\"\n---\nBody.");
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("&lt;tags&gt;", result.Instructions);
        Assert.Contains("&amp;", result.Instructions);
    }

    [Fact]
    public async Task Constructor_WithMultiplePaths_LoadsFromAllAsync()
    {
        // Arrange
        string dir1 = Path.Combine(this._testRoot, "dir1");
        string dir2 = Path.Combine(this._testRoot, "dir2");
        CreateSkillIn(dir1, "skill-a", "Skill A", "Body A.");
        CreateSkillIn(dir2, "skill-b", "Skill B", "Body B.");

        // Act
        var provider = new FileAgentSkillsProvider(new[] { dir1, dir2 });
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Assert
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        Assert.NotNull(result.Instructions);
        Assert.Contains("skill-a", result.Instructions);
        Assert.Contains("skill-b", result.Instructions);
    }

    [Fact]
    public async Task InvokingCoreAsync_PreservesExistingInputToolsAsync()
    {
        // Arrange
        this.CreateSkill("tools-skill", "Tools test", "Body.");
        var provider = new FileAgentSkillsProvider(this._testRoot);

        var existingTool = AIFunctionFactory.Create(() => "test", name: "existing_tool", description: "An existing tool.");
        var inputContext = new AIContext { Tools = new[] { existingTool } };
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — existing tool should be preserved alongside the new skill tools
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("existing_tool", toolNames);
        Assert.Contains("load_skill", toolNames);
        Assert.Contains("read_skill_resource", toolNames);
    }

    [Fact]
    public async Task InvokingCoreAsync_SkillsListIsSortedByNameAsync()
    {
        // Arrange — create skills in reverse alphabetical order
        this.CreateSkill("zulu-skill", "Zulu skill", "Body Z.");
        this.CreateSkill("alpha-skill", "Alpha skill", "Body A.");
        this.CreateSkill("mike-skill", "Mike skill", "Body M.");
        var provider = new FileAgentSkillsProvider(this._testRoot);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — skills should appear in alphabetical order in the prompt
        Assert.NotNull(result.Instructions);
        int alphaIndex = result.Instructions!.IndexOf("alpha-skill", StringComparison.Ordinal);
        int mikeIndex = result.Instructions.IndexOf("mike-skill", StringComparison.Ordinal);
        int zuluIndex = result.Instructions.IndexOf("zulu-skill", StringComparison.Ordinal);
        Assert.True(alphaIndex < mikeIndex, "alpha-skill should appear before mike-skill");
        Assert.True(mikeIndex < zuluIndex, "mike-skill should appear before zulu-skill");
    }

    private void CreateSkill(string name, string description, string body)
    {
        CreateSkillIn(this._testRoot, name, description, body);
    }

    private static void CreateSkillIn(string root, string name, string description, string body)
    {
        string skillDir = Path.Combine(root, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {name}\ndescription: {description}\n---\n{body}");
    }
}
