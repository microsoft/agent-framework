// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentFileSkillScript"/>.
/// </summary>
public sealed class AgentFileSkillScriptTests : IDisposable
{
    private readonly string _testRoot;

    public AgentFileSkillScriptTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "file-skill-script-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._testRoot);
    }

    public void Dispose()
    {
        Directory.Delete(this._testRoot, recursive: true);
    }

    [Fact]
    public async Task RunAsync_SkillIsNotAgentFileSkill_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>("result");
        var script = this.CreateScript("test-script", "/path/to/script.py", RunnerAsync);
        var nonFileSkill = new TestAgentSkill("my-skill", "A skill", "Instructions.");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(nonFileSkill, null, null, CancellationToken.None));
    }

    [Fact]
    public async Task RunAsync_WithAgentFileSkill_DelegatesToRunnerAsync()
    {
        // Arrange
        var runnerCalled = false;
        Task<object?> runnerAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, JsonElement? args, IServiceProvider? sp, CancellationToken ct)
        {
            runnerCalled = true;
            return Task.FromResult<object?>("executed");
        }
        var script = this.CreateScript("run-me", "/scripts/run-me.sh", runnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A file skill"),
            "---\nname: my-skill\n---\nContent",
            "/skills/my-skill");

        // Act
        var result = await script.RunAsync(fileSkill, null, null, CancellationToken.None);

        // Assert
        Assert.True(runnerCalled);
        Assert.Equal("executed", result);
    }

    [Fact]
    public async Task RunAsync_RunnerReceivesCorrectArgumentsAsync()
    {
        // Arrange
        AgentFileSkill? capturedSkill = null;
        AgentFileSkillScript? capturedScript = null;
        Task<object?> runnerAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, JsonElement? args, IServiceProvider? sp, CancellationToken ct)
        {
            capturedSkill = skill;
            capturedScript = scriptArg;
            return Task.FromResult<object?>(null);
        }
        var script = this.CreateScript("capture", "/scripts/capture.py", runnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("owner-skill", "Owner"),
            "Content",
            "/skills/owner-skill");

        // Act
        await script.RunAsync(fileSkill, null, null, CancellationToken.None);

        // Assert
        Assert.Same(fileSkill, capturedSkill);
        Assert.Same(script, capturedScript);
    }

    [Fact]
    public void Script_HasCorrectNameAndPath()
    {
        // Arrange & Act
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = this.CreateScript("my-script", "/path/to/my-script.py", RunnerAsync);

        // Assert
        Assert.Equal("my-script", script.Name);
        Assert.Equal(Path.Combine(this._testRoot, "my-script.py"), script.FullPath);
    }

    [Fact]
    public void ParametersSchema_ReturnsExpectedArraySchema()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = this.CreateScript("my-script", "/path/to/script.py", RunnerAsync);

        // Act
        var schema = script.ParametersSchema;

        // Assert
        Assert.NotNull(schema);
        var raw = schema!.Value.GetRawText();
        Assert.Contains("\"type\":\"array\"", raw);
        Assert.Contains("\"items\":{\"type\":\"string\"}", raw);
    }

    [Fact]
    public async Task Content_WithScripts_AppendsPerScriptEntriesAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script1 = this.CreateScript("build", "/scripts/build.sh", RunnerAsync);
        var script2 = this.CreateScript("deploy", "/scripts/deploy.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            scripts: [script1, script2]);

        // Act
        var content = await fileSkill.GetContentAsync();

        // Assert — content starts with original and appends per-script entries
        Assert.StartsWith("Original content", content);
        Assert.Contains("<available_scripts>", content);
        Assert.Contains("<script name=\"build\">", content);
        Assert.Contains("<script name=\"deploy\">", content);
        Assert.Contains("</available_scripts>", content);

        // A scripts-only skill still emits an empty resources peer so the model knows none are available
        Assert.Contains("<available_resources />", content);
    }

    [Fact]
    public async Task Content_WithoutResourcesOrScripts_EmitsSelfClosingPeersAsync()
    {
        // Arrange
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content only",
            "/skills/my-skill");

        // Act
        var content = await fileSkill.GetContentAsync();

        // Assert — both blocks are always emitted as self-closing elements so the model knows none are available
        Assert.StartsWith("Original content only", content);
        Assert.Contains("<available_resources />", content);
        Assert.Contains("<available_scripts />", content);
    }

    [Fact]
    public async Task Content_WithResources_AppendsResourceEntriesAsync()
    {
        // Arrange
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            resources: [new AgentInlineSkillResource("reference", "value"), new AgentInlineSkillResource("table", "value")]);

        // Act
        var content = await fileSkill.GetContentAsync();

        // Assert — content starts with original and appends per-resource entries so the model knows what is callable
        Assert.StartsWith("Original content", content);
        Assert.Contains("<available_resources>", content);
        Assert.Contains("<resource name=\"reference\"/>", content);
        Assert.Contains("<resource name=\"table\"/>", content);
        Assert.Contains("</available_resources>", content);

        // A resources-only skill still emits an empty scripts peer so the model knows none are available
        Assert.Contains("<available_scripts />", content);
    }

    [Fact]
    public async Task Content_WithResourcesAndScripts_AppendsResourcesBeforeScriptsAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            resources: [new AgentInlineSkillResource("reference", "value")],
            scripts: [this.CreateScript("build", "/scripts/build.sh", RunnerAsync)]);

        // Act
        var content = await fileSkill.GetContentAsync();

        // Assert — resources block precedes scripts block
        var resourcesIndex = content.IndexOf("<available_resources>", StringComparison.Ordinal);
        var scriptsIndex = content.IndexOf("<available_scripts>", StringComparison.Ordinal);
        Assert.True(resourcesIndex >= 0 && scriptsIndex >= 0);
        Assert.True(resourcesIndex < scriptsIndex);
    }

    [Fact]
    public async Task Content_WithScripts_IsCachedAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = this.CreateScript("test", "/scripts/test.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill",
            scripts: [script]);

        // Act
        var content1 = await fileSkill.GetContentAsync();
        var content2 = await fileSkill.GetContentAsync();

        // Assert
        Assert.Same(content1, content2);
    }

    [Fact]
    public async Task RunAsync_ForwardsJsonArrayArgumentsToRunnerAsync()
    {
        // Arrange
        JsonElement? capturedArgs = null;
        Task<object?> runnerAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, JsonElement? args, IServiceProvider? sp, CancellationToken ct)
        {
            capturedArgs = args;
            return Task.FromResult<object?>("done");
        }
        var script = this.CreateScript("array-test", "/scripts/test.sh", runnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill");
        using var arrayArgsDoc = JsonDocument.Parse("""["arg1","arg2","arg3"]""");
        var arrayArgs = arrayArgsDoc.RootElement;

        // Act
        await script.RunAsync(fileSkill, arrayArgs, null, CancellationToken.None);

        // Assert — the raw JSON array is forwarded unchanged
        Assert.NotNull(capturedArgs);
        Assert.Equal(JsonValueKind.Array, capturedArgs!.Value.ValueKind);
        Assert.Equal("""["arg1","arg2","arg3"]""", capturedArgs.Value.GetRawText());
    }

    [Fact]
    public async Task RunAsync_ForwardsServiceProviderToRunnerAsync()
    {
        // Arrange
        IServiceProvider? capturedProvider = null;
        Task<object?> runnerAsync(AgentFileSkill skill, AgentFileSkillScript scriptArg, JsonElement? args, IServiceProvider? sp, CancellationToken ct)
        {
            capturedProvider = sp;
            return Task.FromResult<object?>("done");
        }
        var script = this.CreateScript("sp-test", "/scripts/test.sh", runnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill");
        var mockProvider = new TestServiceProvider();

        // Act
        await script.RunAsync(fileSkill, null, mockProvider, CancellationToken.None);

        // Assert
        Assert.Same(mockProvider, capturedProvider);
    }

    [Fact]
    public async Task RunAsync_NoRunner_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange — create script without a runner
        var script = this.CreateScript("no-runner", "/scripts/test.sh", runner: null);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(fileSkill, null, null, CancellationToken.None));
    }

    [Fact]
    public async Task Content_WithScripts_ContainsDefaultParametersSchemaAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = this.CreateScript("test", "/scripts/test.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            scripts: [script]);

        // Act
        var content = await fileSkill.GetContentAsync();

        // Assert — the appended block contains the actual default schema from AgentFileSkillScript
        Assert.Contains("""{"type":"array","items":{"type":"string"}}""", content);
    }

    /// <summary>
    /// Helper to create an <see cref="AgentFileSkillScript"/> rooted in the test directory.
    /// </summary>
    private AgentFileSkillScript CreateScript(string name, string fullPath, AgentFileSkillScriptRunner? runner)
    {
        string resolvedPath = Path.Combine(this._testRoot, Path.GetFileName(fullPath));
        File.WriteAllText(resolvedPath, string.Empty);

        return new AgentFileSkillScript(name, resolvedPath, new AgentFileSkillPathScope(this._testRoot, this._testRoot), runner);
    }

    /// <summary>
    /// Minimal <see cref="IServiceProvider"/> for testing service forwarding.
    /// </summary>
    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }
}
