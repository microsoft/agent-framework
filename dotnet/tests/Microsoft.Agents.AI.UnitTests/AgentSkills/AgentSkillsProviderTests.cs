// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for the <see cref="AgentSkillsProvider"/> class with <see cref="AgentFileSkillsSource"/>.
/// </summary>
public sealed class AgentSkillsProviderTests : IDisposable
{
    private static readonly AgentFileSkillScriptRunner s_noOpExecutor = (skill, script, args, sp, ct) => Task.FromResult<object?>(null);
    private readonly string _testRoot;
    private readonly TestAIAgent _agent = new();

    public AgentSkillsProviderTests()
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
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
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
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
        var inputContext = new AIContext { Instructions = "Base instructions" };
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("Base instructions", result.Instructions);
        Assert.Contains("provider-skill", result.Instructions);
        Assert.Contains("Provider skill test", result.Instructions);

        // Should have load_skill tool (no resources, so no read_skill_resource)
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("load_skill", toolNames);
        Assert.DoesNotContain("read_skill_resource", toolNames);
    }

    [Fact]
    public async Task InvokingCoreAsync_NullInputInstructions_SetsInstructionsAsync()
    {
        // Arrange
        this.CreateSkill("null-instr-skill", "Null instruction test", "Body.");
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
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
        var options = new AgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Custom template: {skills}\n{resource_instructions}\n{script_instructions}"
        };
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor), options);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.StartsWith("Custom template:", result.Instructions);
        Assert.Contains("custom-prompt-skill", result.Instructions);
        Assert.Contains("Custom prompt", result.Instructions);
    }

    [Fact]
    public void Constructor_PromptWithoutSkillsPlaceholder_ThrowsArgumentException()
    {
        // Arrange
        var options = new AgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "No skills placeholder here {resource_instructions} {script_instructions}"
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() =>
            new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor), options));
        Assert.Contains("{skills}", ex.Message);
        Assert.Equal("options", ex.ParamName);
    }

    [Fact]
    public void Constructor_PromptWithoutRunnerInstructionsPlaceholder_ThrowsArgumentException()
    {
        // Arrange
        var options = new AgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Has skills {skills} but no runner instructions {resource_instructions}"
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() =>
            new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor), options));
        Assert.Contains("{script_instructions}", ex.Message);
        Assert.Equal("options", ex.ParamName);
    }

    [Fact]
    public void Constructor_PromptWithBothPlaceholders_Succeeds()
    {
        // Arrange
        var options = new AgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Skills: {skills}\nResources: {resource_instructions}\nRunner: {script_instructions}"
        };

        // Act — should not throw
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor), options);

        // Assert
        Assert.NotNull(provider);
    }

    [Fact]
    public void Constructor_PromptWithoutResourceInstructionsPlaceholder_ThrowsArgumentException()
    {
        // Arrange
        var options = new AgentSkillsProviderOptions
        {
            SkillsInstructionPrompt = "Has skills {skills} and runner {script_instructions} but no resource instructions"
        };

        // Act & Assert
        var ex = Assert.Throws<ArgumentException>(() =>
            new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor), options));
        Assert.Contains("{resource_instructions}", ex.Message);
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
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
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
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(new[] { dir1, dir2 }, s_noOpExecutor));
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
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));

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
    }

    [Fact]
    public async Task InvokingCoreAsync_SkillsListIsSortedByNameAsync()
    {
        // Arrange — create skills in reverse alphabetical order
        this.CreateSkill("zulu-skill", "Zulu skill", "Body Z.");
        this.CreateSkill("alpha-skill", "Alpha skill", "Body A.");
        this.CreateSkill("mike-skill", "Mike skill", "Body M.");
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
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

    [Fact]
    public async Task ProvideAIContextAsync_ConcurrentCalls_LoadsSkillsOnlyOnceAsync()
    {
        // Arrange
        var source = new CountingAgentSkillsSource(
        [
            new AgentInlineSkill("concurrent-skill", "Concurrent test", "Body.")
        ]);
        var provider = new AgentSkillsProvider(source);

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act — invoke concurrently from multiple threads
        var tasks = Enumerable.Range(0, 10)
            .Select(_ => provider.InvokingAsync(invokingContext, CancellationToken.None).AsTask())
            .ToArray();
        await Task.WhenAll(tasks);

        // Assert — GetSkillsAsync should have been called exactly once (provider-level caching)
        Assert.Equal(1, source.GetSkillsCallCount);
    }

    [Fact]
    public async Task InvokingCoreAsync_WithScripts_IncludesRunSkillScriptToolAsync()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "script-skill");
        Directory.CreateDirectory(Path.Combine(skillDir, "scripts"));
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: script-skill\ndescription: Skill with scripts\n---\nBody.");
        File.WriteAllText(
            Path.Combine(skillDir, "scripts", "test.py"),
            "print('hello')");

        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var provider = new AgentSkillsProvider(source);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("run_skill_script", toolNames);
        Assert.Contains("load_skill", toolNames);
    }

    [Fact]
    public async Task InvokingCoreAsync_WithoutScripts_NoRunSkillScriptToolAsync()
    {
        // Arrange
        this.CreateSkill("no-script-skill", "No scripts", "Body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var provider = new AgentSkillsProvider(source);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.DoesNotContain("run_skill_script", toolNames);
    }

    [Fact]
    public void Build_WithFileSkillsButNoExecutor_ThrowsInvalidOperationException()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder()
            .UseFileSkill(this._testRoot);

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => builder.Build());
    }

    [Fact]
    public async Task Builder_UseFileSkillWithOptions_DiscoverSkillsAsync()
    {
        // Arrange
        this.CreateSkill("opts-skill", "Options skill", "Options body.");
        var options = new AgentFileSkillsSourceOptions();
        var provider = new AgentSkillsProviderBuilder()
            .UseFileSkill(this._testRoot, options)
            .UseFileScriptRunner(s_noOpExecutor)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        // Act
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("opts-skill", result.Instructions);
    }

    [Fact]
    public async Task Builder_UseFileSkillsWithOptions_DiscoverMultipleSkillsAsync()
    {
        // Arrange
        string dir1 = Path.Combine(this._testRoot, "multi-opts-1");
        string dir2 = Path.Combine(this._testRoot, "multi-opts-2");
        CreateSkillIn(dir1, "skill-x", "Skill X", "Body X.");
        CreateSkillIn(dir2, "skill-y", "Skill Y", "Body Y.");

        var options = new AgentFileSkillsSourceOptions();
        var provider = new AgentSkillsProviderBuilder()
            .UseFileSkills(new[] { dir1, dir2 }, options)
            .UseFileScriptRunner(s_noOpExecutor)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        // Act
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("skill-x", result.Instructions);
        Assert.Contains("skill-y", result.Instructions);
    }

    [Fact]
    public async Task Builder_UseFileSkillWithOptionsResourceFilter_FiltersResourcesAsync()
    {
        // Arrange — create a skill with both .md and .json resources
        string skillDir = Path.Combine(this._testRoot, "res-filter-opts");
        CreateSkillIn(skillDir, "filter-skill", "Filter test", "Filter body.");
        File.WriteAllText(Path.Combine(skillDir, "data.json"), "{}", System.Text.Encoding.UTF8);
        File.WriteAllText(Path.Combine(skillDir, "notes.txt"), "notes", System.Text.Encoding.UTF8);

        // Only allow .json resources
        var options = new AgentFileSkillsSourceOptions
        {
            AllowedResourceExtensions = [".json"],
        };
        var source = new AgentFileSkillsSource(skillDir, s_noOpExecutor, options);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var fileSkill = Assert.IsType<AgentFileSkill>(skills[0]);
        Assert.All(fileSkill.Resources, r => Assert.EndsWith(".json", r.Name));
    }

    private void CreateSkill(string name, string description, string body)
    {
        CreateSkillIn(this._testRoot, name, description, body);
    }

    [Fact]
    public async Task LoadSkill_DefaultOptions_ReturnsFullContentAsync()
    {
        // Arrange
        this.CreateSkill("content-skill", "Content test", "Skill body.");
        var provider = new AgentSkillsProvider(new AgentFileSkillsSource(this._testRoot, s_noOpExecutor));
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;

        // Act
        var content = await loadSkillTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?> { ["skillName"] = "content-skill" }));

        // Assert — should contain frontmatter and body
        var text = content!.ToString()!;
        Assert.Contains("---", text);
        Assert.Contains("name: content-skill", text);
        Assert.Contains("Skill body.", text);
    }

    [Fact]
    public async Task Builder_UseFileScriptRunnerAfterUseFileSkills_RunnerIsUsedAsync()
    {
        // Arrange — create a skill with a script file
        string skillDir = Path.Combine(this._testRoot, "builder-skill");
        Directory.CreateDirectory(Path.Combine(skillDir, "scripts"));
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: builder-skill\ndescription: Builder test\n---\nBody.");
        File.WriteAllText(
            Path.Combine(skillDir, "scripts", "run.py"),
            "print('ok')");

        var executorCalled = false;

        // Act — call UseFileScriptRunner AFTER UseFileSkill (the bug scenario)
        var provider = new AgentSkillsProviderBuilder()
            .UseFileSkill(this._testRoot)
            .UseFileScriptRunner((skill, script, args, sp, ct) =>
            {
                executorCalled = true;
                return Task.FromResult<object?>("executed");
            })
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — run_skill_script tool should be present and executor should work
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("run_skill_script", toolNames);

        var runScriptTool = result.Tools!.First(t => t.Name == "run_skill_script") as AIFunction;
        await runScriptTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?>
        {
            ["skillName"] = "builder-skill",
            ["scriptName"] = "scripts/run.py",
        }));

        Assert.True(executorCalled);
    }

    [Fact]
    public async Task RunSkillScript_ForwardsJsonArgumentsAndServiceProviderToRunnerAsync()
    {
        // Arrange — create a skill with a script file
        string skillDir = Path.Combine(this._testRoot, "fwd-skill");
        Directory.CreateDirectory(Path.Combine(skillDir, "scripts"));
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: fwd-skill\ndescription: Forwarding test\n---\nBody.");
        File.WriteAllText(
            Path.Combine(skillDir, "scripts", "run.py"),
            "print('ok')");

        JsonElement? capturedArgs = null;
        IServiceProvider? capturedServiceProvider = null;

        var provider = new AgentSkillsProviderBuilder()
            .UseFileSkill(this._testRoot)
            .UseFileScriptRunner((skill, script, args, sp, ct) =>
            {
                capturedArgs = args;
                capturedServiceProvider = sp;
                return Task.FromResult<object?>("executed");
            })
            .Build();

        var mockServiceProvider = new TestServiceProvider();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var runScriptTool = result.Tools!.First(t => t.Name == "run_skill_script") as AIFunction;

        // Act — invoke with JsonElement arguments and a service provider
        using var argsJsonDoc = JsonDocument.Parse("""["arg1","arg2"]""");
        var argsJson = argsJsonDoc.RootElement;
        await runScriptTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?>
        {
            ["skillName"] = "fwd-skill",
            ["scriptName"] = "scripts/run.py",
            ["arguments"] = argsJson,
        })
        {
            Services = mockServiceProvider,
        });

        // Assert — JsonElement arguments and service provider are forwarded to the runner
        Assert.NotNull(capturedArgs);
        Assert.Equal(JsonValueKind.Array, capturedArgs!.Value.ValueKind);
        Assert.Equal("""["arg1","arg2"]""", capturedArgs.Value.GetRawText());
        Assert.Same(mockServiceProvider, capturedServiceProvider);
    }

    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }

    private static void CreateSkillIn(string root, string name, string description, string body)
    {
        string skillDir = Path.Combine(root, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {name}\ndescription: {description}\n---\n{body}");
    }

    [Fact]
    public async Task Build_WithCachingDisabled_ReloadsSkillsOnEachCallAsync()
    {
        // Arrange
        var source = new CountingAgentSkillsSource(
        [
            new AgentInlineSkill("no-cache-skill", "No cache test", "Body.")
        ]);
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — source should be called more than once since caching is disabled
        Assert.True(source.GetSkillsCallCount > 1);
    }

    [Fact]
    public async Task Build_WithCachingEnabled_CachesSkillsAsync()
    {
        // Arrange
        var source = new CountingAgentSkillsSource(
        [
            new AgentInlineSkill("cached-skill", "Cached test", "Body.")
        ]);
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source)
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — source should be called exactly once (caching is on by default)
        Assert.Equal(1, source.GetSkillsCallCount);
    }

    [Fact]
    public async Task Build_DefaultOptions_CachesSkillsAsync()
    {
        // Arrange
        var source = new CountingAgentSkillsSource(
        [
            new AgentInlineSkill("default-skill", "Default test", "Body.")
        ]);
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source)
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — default behavior caches
        Assert.Equal(1, source.GetSkillsCallCount);
    }

    [Fact]
    public async Task Build_PreservesSourceRegistrationOrderAsync()
    {
        // Arrange — register file, inline, file in that order
        string dir1 = Path.Combine(this._testRoot, "dir1");
        string dir2 = Path.Combine(this._testRoot, "dir2");
        CreateSkillIn(dir1, "file-skill-1", "First file skill", "Body 1.");
        CreateSkillIn(dir2, "file-skill-2", "Second file skill", "Body 2.");

        var inlineSkill = new AgentInlineSkill("inline-skill", "Inline skill", "Body inline.");

        var provider = new AgentSkillsProviderBuilder()
            .UseFileSkill(dir1)
            .UseSkills(inlineSkill)
            .UseFileSkill(dir2)
            .UseFileScriptRunner(s_noOpExecutor)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — all three skills should be present in alphabetical order in the prompt
        Assert.NotNull(result.Instructions);
        var instructions = result.Instructions!;
        var indexFileSkill1 = instructions.IndexOf("file-skill-1", StringComparison.Ordinal);
        var indexFileSkill2 = instructions.IndexOf("file-skill-2", StringComparison.Ordinal);
        var indexInlineSkill = instructions.IndexOf("inline-skill", StringComparison.Ordinal);

        Assert.True(indexFileSkill1 >= 0, "file-skill-1 should be present in the instructions.");
        Assert.True(indexFileSkill2 >= 0, "file-skill-2 should be present in the instructions.");
        Assert.True(indexInlineSkill >= 0, "inline-skill should be present in the instructions.");

        Assert.True(indexFileSkill1 < indexFileSkill2, "file-skill-1 should appear before file-skill-2.");
        Assert.True(indexFileSkill2 < indexInlineSkill, "file-skill-2 should appear before inline-skill.");
    }

    [Fact]
    public async Task Build_MixedSources_AllSkillsDiscoveredAsync()
    {
        // Arrange — use UseSource, UseSkill, and UseFileSkill in mixed order
        string dir = Path.Combine(this._testRoot, "mixed-dir");
        CreateSkillIn(dir, "file-skill", "File skill", "Body file.");

        var inlineSkill = new AgentInlineSkill("inline-skill", "Inline skill", "Body inline.");
        var customSource = new CountingAgentSkillsSource(
        [
            new AgentInlineSkill("custom-skill", "Custom source skill", "Body custom.")
        ]);

        var provider = new AgentSkillsProviderBuilder()
            .UseSource(customSource)
            .UseSkills(inlineSkill)
            .UseFileSkill(dir)
            .UseFileScriptRunner(s_noOpExecutor)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — all skills from all sources are present
        Assert.NotNull(result.Instructions);
        Assert.Contains("custom-skill", result.Instructions);
        Assert.Contains("inline-skill", result.Instructions);
        Assert.Contains("file-skill", result.Instructions);
    }

    [Fact]
    public async Task InvokingCoreAsync_WithScriptsAndScriptApproval_WrapsRunScriptToolAsync()
    {
        // Arrange — create a skill with a script and enable ScriptApproval
        string skillDir = Path.Combine(this._testRoot, "approval-skill");
        Directory.CreateDirectory(Path.Combine(skillDir, "scripts"));
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: approval-skill\ndescription: Approval test\n---\nBody.");
        File.WriteAllText(
            Path.Combine(skillDir, "scripts", "run.py"),
            "print('hello')");

        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var options = new AgentSkillsProviderOptions { ScriptApproval = true };
        var provider = new AgentSkillsProvider(source, options);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — run_skill_script tool should be wrapped in ApprovalRequiredAIFunction
        Assert.NotNull(result.Tools);
        var scriptTool = result.Tools!.FirstOrDefault(t => t.Name == "run_skill_script");
        Assert.NotNull(scriptTool);
        Assert.IsType<ApprovalRequiredAIFunction>(scriptTool);
    }

    [Fact]
    public async Task InvokingCoreAsync_WithScriptsNoScriptApproval_DoesNotWrapRunScriptToolAsync()
    {
        // Arrange — create a skill with a script, default options (no approval)
        string skillDir = Path.Combine(this._testRoot, "no-approval-skill");
        Directory.CreateDirectory(Path.Combine(skillDir, "scripts"));
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: no-approval-skill\ndescription: No approval test\n---\nBody.");
        File.WriteAllText(
            Path.Combine(skillDir, "scripts", "run.py"),
            "print('hello')");

        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var provider = new AgentSkillsProvider(source);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — run_skill_script tool should NOT be wrapped
        Assert.NotNull(result.Tools);
        var scriptTool = result.Tools!.FirstOrDefault(t => t.Name == "run_skill_script");
        Assert.NotNull(scriptTool);
        Assert.IsNotType<ApprovalRequiredAIFunction>(scriptTool);
    }

    [Fact]
    public async Task InvokingCoreAsync_MultipleInvocations_ToolsAreSharedWhenCachedAsync()
    {
        // Arrange — with default caching, tools should be the same reference
        this.CreateSkill("cached-tools-skill", "Cached tools test", "Body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var provider = new AgentSkillsProvider(source);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result1 = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var result2 = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — tool lists should be the same reference (cached)
        Assert.NotNull(result1.Tools);
        Assert.NotNull(result2.Tools);
        Assert.Same(result1.Tools, result2.Tools);
    }

    [Fact]
    public async Task InvokingCoreAsync_MultipleInvocations_ToolsAreNotSharedWhenCachingDisabledAsync()
    {
        // Arrange — with caching disabled, tools should be rebuilt per invocation
        this.CreateSkill("fresh-tools-skill", "Fresh tools test", "Body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var options = new AgentSkillsProviderOptions { DisableCaching = true };
        var provider = new AgentSkillsProvider(source, options);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result1 = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var result2 = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — tool lists should not be the same reference
        Assert.NotNull(result1.Tools);
        Assert.NotNull(result2.Tools);
        Assert.NotSame(result1.Tools, result2.Tools);
    }

    [Fact]
    public async Task Constructor_SingleDirectory_DiscoverFileSkillsAsync()
    {
        // Arrange
        this.CreateSkill("file-ctor-skill", "File ctor test", "File body.");
        var provider = new AgentSkillsProvider(this._testRoot, s_noOpExecutor);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("file-ctor-skill", result.Instructions);
        Assert.NotNull(result.Tools);
        Assert.Contains(result.Tools!, t => t.Name == "load_skill");
    }

    [Fact]
    public async Task Constructor_MultipleDirectories_DiscoverFileSkillsAsync()
    {
        // Arrange
        string dir1 = Path.Combine(this._testRoot, "dir1");
        string dir2 = Path.Combine(this._testRoot, "dir2");
        Directory.CreateDirectory(dir1);
        Directory.CreateDirectory(dir2);
        CreateSkillIn(dir1, "skill-a", "Skill A", "Body A.");
        CreateSkillIn(dir2, "skill-b", "Skill B", "Body B.");

        var provider = new AgentSkillsProvider(new[] { dir1, dir2 }, s_noOpExecutor);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("skill-a", result.Instructions);
        Assert.Contains("skill-b", result.Instructions);
    }

    [Fact]
    public async Task Constructor_MultipleDirectories_DeduplicatesSkillsByNameAsync()
    {
        // Arrange — same skill name in two directories
        string dir1 = Path.Combine(this._testRoot, "dup1");
        string dir2 = Path.Combine(this._testRoot, "dup2");
        Directory.CreateDirectory(dir1);
        Directory.CreateDirectory(dir2);
        CreateSkillIn(dir1, "dup-skill", "First", "Body 1.");
        CreateSkillIn(dir2, "dup-skill", "Second", "Body 2.");

        var provider = new AgentSkillsProvider(new[] { dir1, dir2 }, s_noOpExecutor);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;
        var content = await loadSkillTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?> { ["skillName"] = "dup-skill" }));

        // Assert — only first occurrence should survive
        Assert.NotNull(content);
        Assert.Contains("Body 1.", content!.ToString()!);
    }

    [Fact]
    public async Task Constructor_InlineSkillsParams_ProvidesSkillsAsync()
    {
        // Arrange
        var skill1 = new AgentInlineSkill("inline-a", "Inline A", "Instructions A.");
        var skill2 = new AgentInlineSkill("inline-b", "Inline B", "Instructions B.");
        var provider = new AgentSkillsProvider(skill1, skill2);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("inline-a", result.Instructions);
        Assert.Contains("inline-b", result.Instructions);
    }

    [Fact]
    public async Task Constructor_InlineSkillsEnumerable_ProvidesSkillsAsync()
    {
        // Arrange
        var skills = new List<AgentInlineSkill>
        {
            new("enum-inline-a", "Inline A", "Instructions A."),
            new("enum-inline-b", "Inline B", "Instructions B."),
        };
        var provider = new AgentSkillsProvider(skills);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("enum-inline-a", result.Instructions);
        Assert.Contains("enum-inline-b", result.Instructions);
    }

    [Fact]
    public async Task Constructor_InlineSkills_DeduplicatesAsync()
    {
        // Arrange — two inline skills with the same name
        var skill1 = new AgentInlineSkill("dup-inline", "First", "First instructions.");
        var skill2 = new AgentInlineSkill("dup-inline", "Second", "Second instructions.");
        var provider = new AgentSkillsProvider(skill1, skill2);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;
        var content = await loadSkillTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?> { ["skillName"] = "dup-inline" }));

        // Assert — only one occurrence (first)
        Assert.Contains("First instructions.", content!.ToString()!);
    }

    [Fact]
    public async Task Constructor_ClassSkillsParams_ProvidesSkillsAsync()
    {
        // Arrange
        var skill = new TestClassSkill("class-a", "Class A", "Class instructions.");
        var provider = new AgentSkillsProvider(skill);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("class-a", result.Instructions);
    }

    [Fact]
    public async Task Constructor_ClassSkillsEnumerable_ProvidesSkillsAsync()
    {
        // Arrange
        var skills = new List<AgentSkill>
        {
            new TestClassSkill("enum-class-a", "Class A", "Instructions A."),
            new TestClassSkill("enum-class-b", "Class B", "Instructions B."),
        };
        var provider = new AgentSkillsProvider(skills);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("enum-class-a", result.Instructions);
        Assert.Contains("enum-class-b", result.Instructions);
    }

    [Fact]
    public async Task Constructor_ClassSkills_DeduplicatesAsync()
    {
        // Arrange — two class skills with the same name
        var skill1 = new TestClassSkill("dup-class", "First", "First instructions.");
        var skill2 = new TestClassSkill("dup-class", "Second", "Second instructions.");
        var provider = new AgentSkillsProvider(skill1, skill2);
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);
        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;
        var content = await loadSkillTool!.InvokeAsync(new AIFunctionArguments(new Dictionary<string, object?> { ["skillName"] = "dup-class" }));

        // Assert — only first occurrence survives
        Assert.Contains("First instructions.", content!.ToString()!);
    }

    /// <summary>
    /// A test skill source that counts how many times <see cref="GetSkillsAsync"/> is called.
    /// </summary>
    private sealed class CountingAgentSkillsSource : AgentSkillsSource
    {
        private readonly IList<AgentSkill> _skills;
        private int _callCount;

        public CountingAgentSkillsSource(IList<AgentSkill> skills)
        {
            this._skills = skills;
        }

        public int GetSkillsCallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult(this._skills);
        }
    }

    private sealed class TestClassSkill : AgentClassSkill<TestClassSkill>
    {
        private readonly string _instructions;

        public TestClassSkill(string name, string description, string instructions)
        {
            this.Frontmatter = new AgentSkillFrontmatter(name, description);
            this._instructions = instructions;
        }

        public override AgentSkillFrontmatter Frontmatter { get; }

        protected override string Instructions => this._instructions;

        public override IReadOnlyList<AgentSkillResource>? Resources => null;

        public override IReadOnlyList<AgentSkillScript>? Scripts => null;
    }
}
