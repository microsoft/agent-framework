// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentFileSkillScript"/>.
/// </summary>
public sealed class AgentFileSkillScriptTests
{
    [Fact]
    public async Task RunAsync_SkillIsNotAgentFileSkill_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>("result");
        var script = CreateScript("test-script", "/path/to/script.py", RunnerAsync);
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
        var script = CreateScript("run-me", "/scripts/run-me.sh", runnerAsync);
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
        var script = CreateScript("capture", "/scripts/capture.py", runnerAsync);
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
        var script = CreateScript("my-script", "/path/to/my-script.py", RunnerAsync);

        // Assert
        Assert.Equal("my-script", script.Name);
        Assert.Equal("/path/to/my-script.py", script.FullPath);
    }

    [Fact]
    public void ParametersSchema_ReturnsExpectedArraySchema()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = CreateScript("my-script", "/path/to/script.py", RunnerAsync);

        // Act
        var schema = script.ParametersSchema;

        // Assert
        Assert.NotNull(schema);
        var raw = schema!.Value.GetRawText();
        Assert.Contains("\"type\":\"array\"", raw);
        Assert.Contains("\"items\":{\"type\":\"string\"}", raw);
    }

    [Fact]
    public void Content_WithScripts_AppendsPerScriptEntries()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script1 = CreateScript("build", "/scripts/build.sh", RunnerAsync);
        var script2 = CreateScript("deploy", "/scripts/deploy.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            scripts: [script1, script2]);

        // Act
        var content = fileSkill.Content;

        // Assert — content starts with original and appends per-script entries
        Assert.StartsWith("Original content", content);
        Assert.Contains("<scripts>", content);
        Assert.Contains("<script name=\"build\">", content);
        Assert.Contains("<script name=\"deploy\">", content);
        Assert.Contains("<parameters_schema>", content);
        Assert.Contains("</scripts>", content);
    }

    [Fact]
    public void Content_WithoutScripts_ReturnsOriginalContent()
    {
        // Arrange
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content only",
            "/skills/my-skill");

        // Act
        var content = fileSkill.Content;

        // Assert
        Assert.Equal("Original content only", content);
    }

    [Fact]
    public void Content_WithScripts_IsCached()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = CreateScript("test", "/scripts/test.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill",
            scripts: [script]);

        // Act
        var content1 = fileSkill.Content;
        var content2 = fileSkill.Content;

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
        var script = CreateScript("array-test", "/scripts/test.sh", runnerAsync);
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
        var script = CreateScript("sp-test", "/scripts/test.sh", runnerAsync);
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
        var script = CreateScript("no-runner", "/scripts/test.sh", runner: null);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Content",
            "/skills/my-skill");

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => script.RunAsync(fileSkill, null, null, CancellationToken.None));
    }

    [Fact]
    public void Content_WithScripts_ContainsDefaultParametersSchema()
    {
        // Arrange
        static Task<object?> RunnerAsync(AgentFileSkill s, AgentFileSkillScript sc, JsonElement? a, IServiceProvider? sp, CancellationToken ct) => Task.FromResult<object?>(null);
        var script = CreateScript("test", "/scripts/test.sh", RunnerAsync);
        var fileSkill = new AgentFileSkill(
            new AgentSkillFrontmatter("my-skill", "A skill"),
            "Original content",
            "/skills/my-skill",
            scripts: [script]);

        // Act
        var content = fileSkill.Content;

        // Assert — the appended block contains the actual default schema from AgentFileSkillScript
        Assert.Contains("""{"type":"array","items":{"type":"string"}}""", content);
    }

    /// <summary>
    /// Helper to create an <see cref="AgentFileSkillScript"/> via reflection since the constructor is internal.
    /// </summary>
    private static AgentFileSkillScript CreateScript(string name, string fullPath, AgentFileSkillScriptRunner? runner)
    {
        var ctor = typeof(AgentFileSkillScript).GetConstructor(
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance,
            null,
            [typeof(string), typeof(string), typeof(AgentFileSkillScriptRunner)],
            null) ?? throw new InvalidOperationException("Could not find internal constructor.");

        return (AgentFileSkillScript)ctor.Invoke([name, fullPath, runner]);
    }

    /// <summary>
    /// Minimal <see cref="IServiceProvider"/> for testing service forwarding.
    /// </summary>
    private sealed class TestServiceProvider : IServiceProvider
    {
        public object? GetService(Type serviceType) => null;
    }
}
