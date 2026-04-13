// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for script discovery and execution in <see cref="AgentFileSkillsSource"/>.
/// </summary>
public sealed class AgentFileSkillsSourceScriptTests : IDisposable
{
    private static readonly string[] s_rubyExtension = new[] { ".rb" };
    private static readonly AgentFileSkillScriptRunner s_noOpExecutor = (skill, script, args, ct) => Task.FromResult<object?>(null);

    private readonly string _testRoot;

    public AgentFileSkillsSourceScriptTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "skills-source-script-tests-" + Guid.NewGuid().ToString("N"));
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
    public async Task GetSkillsAsync_WithScriptFiles_DiscoversScriptsAsync()
    {
        // Arrange
        CreateSkillWithScript(this._testRoot, "my-skill", "A test skill", "Body.", "scripts/convert.py", "print('hello')");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
        var skill = skills[0];
        Assert.NotNull(skill.Scripts);
        Assert.Single(skill.Scripts!);
        Assert.Equal("scripts/convert.py", skill.Scripts![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_WithMultipleScriptExtensions_DiscoversAllAsync()
    {
        // Arrange
        string skillDir = CreateSkillDir(this._testRoot, "multi-ext-skill", "Multi-extension skill", "Body.");
        CreateFile(skillDir, "scripts/run.py", "print('py')");
        CreateFile(skillDir, "scripts/run.sh", "echo 'sh'");
        CreateFile(skillDir, "scripts/run.js", "console.log('js')");
        CreateFile(skillDir, "scripts/run.ps1", "Write-Host 'ps'");
        CreateFile(skillDir, "scripts/run.cs", "Console.WriteLine();");
        CreateFile(skillDir, "scripts/run.csx", "Console.WriteLine();");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
        var scriptNames = skills[0].Scripts!.Select(s => s.Name).OrderBy(n => n, StringComparer.Ordinal).ToList();
        Assert.Equal(6, scriptNames.Count);
        Assert.Contains("scripts/run.cs", scriptNames);
        Assert.Contains("scripts/run.csx", scriptNames);
        Assert.Contains("scripts/run.js", scriptNames);
        Assert.Contains("scripts/run.ps1", scriptNames);
        Assert.Contains("scripts/run.py", scriptNames);
        Assert.Contains("scripts/run.sh", scriptNames);
    }

    [Fact]
    public async Task GetSkillsAsync_NonScriptExtensionsAreNotDiscoveredAsync()
    {
        // Arrange
        string skillDir = CreateSkillDir(this._testRoot, "no-script-skill", "Non-script skill", "Body.");
        CreateFile(skillDir, "scripts/data.txt", "text data");
        CreateFile(skillDir, "scripts/config.json", "{}");
        CreateFile(skillDir, "scripts/notes.md", "# Notes");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
        Assert.Empty(skills[0].Scripts!);
    }

    [Fact]
    public async Task GetSkillsAsync_NoScriptFiles_ReturnsEmptyScriptsAsync()
    {
        // Arrange
        CreateSkillDir(this._testRoot, "no-scripts", "No scripts skill", "Body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
        Assert.NotNull(skills[0].Scripts);
        Assert.Empty(skills[0].Scripts!);
    }

    [Fact]
    public async Task GetSkillsAsync_ScriptsOutsideScriptsDir_AreNotDiscoveredAsync()
    {
        // Arrange — scripts outside configured directories are not discovered; only files directly
        // inside the configured directory are picked up (no subdirectory recursion)
        string skillDir = CreateSkillDir(this._testRoot, "root-scripts", "Root scripts skill", "Body.");
        CreateFile(skillDir, "convert.py", "print('root')");
        CreateFile(skillDir, "tools/helper.sh", "echo 'helper'");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert — neither file is in the default scripts/ directory, so no scripts are discovered
        Assert.Single(skills);
        Assert.Empty(skills[0].Scripts!);
    }

    [Fact]
    public async Task GetSkillsAsync_WithRunner_ScriptsCanRunAsync()
    {
        // Arrange
        CreateSkillWithScript(this._testRoot, "exec-skill", "Executor test", "Body.", "scripts/test.py", "print('ok')");
        var executorCalled = false;
        var source = new AgentFileSkillsSource(
            this._testRoot,
            (skill, script, args, ct) =>
            {
                executorCalled = true;
                Assert.Equal("exec-skill", skill.Frontmatter.Name);
                Assert.Equal("scripts/test.py", script.Name);
                Assert.Equal(Path.GetFullPath(Path.Combine(this._testRoot, "exec-skill", "scripts", "test.py")), script.FullPath);
                return Task.FromResult<object?>("executed");
            });

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);
        var scriptResult = await skills[0].Scripts![0].RunAsync(skills[0], new AIFunctionArguments(), CancellationToken.None);

        // Assert
        Assert.True(executorCalled);
        Assert.Equal("executed", scriptResult);
    }

    [Fact]
    public void Constructor_NullExecutor_DoesNotThrow()
    {
        // Arrange & Act & Assert — null runner is allowed when skills have no scripts
        var source = new AgentFileSkillsSource(this._testRoot, null);
        Assert.NotNull(source);
    }

    [Fact]
    public async Task GetSkillsAsync_ScriptsWithNoRunner_ThrowsOnRunAsync()
    {
        // Arrange
        string skillDir = CreateSkillDir(this._testRoot, "no-runner-skill", "No runner", "Body.");
        CreateFile(skillDir, "scripts/run.sh", "echo 'hello'");
        var source = new AgentFileSkillsSource(this._testRoot, scriptRunner: null);

        // Act — discovery succeeds even without a runner
        var skills = await source.GetSkillsAsync(CancellationToken.None);
        var script = skills[0].Scripts![0];

        // Assert — running the script throws because no runner was provided
        await Assert.ThrowsAsync<InvalidOperationException>(() => script.RunAsync(skills[0], new AIFunctionArguments(), CancellationToken.None));
    }

    [Fact]
    public async Task GetSkillsAsync_CustomScriptExtensions_OnlyDiscoversMatchingAsync()
    {
        // Arrange
        string skillDir = CreateSkillDir(this._testRoot, "custom-ext-skill", "Custom extensions", "Body.");
        CreateFile(skillDir, "scripts/run.py", "print('py')");
        CreateFile(skillDir, "scripts/run.rb", "puts 'rb'");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { AllowedScriptExtensions = s_rubyExtension });

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(skills);
        Assert.Single(skills[0].Scripts!);
        Assert.Equal("scripts/run.rb", skills[0].Scripts![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_ExecutorReceivesArgumentsAsync()
    {
        // Arrange
        CreateSkillWithScript(this._testRoot, "args-skill", "Args test", "Body.", "scripts/test.py", "print('ok')");
        AIFunctionArguments? capturedArgs = null;
        var source = new AgentFileSkillsSource(
            this._testRoot,
            (skill, script, args, ct) =>
            {
                capturedArgs = args;
                return Task.FromResult<object?>("done");
            });

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);
        var arguments = new AIFunctionArguments
        {
            ["value"] = 26.2,
            ["factor"] = 1.60934
        };
        await skills[0].Scripts![0].RunAsync(skills[0], arguments, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedArgs);
        Assert.Equal(26.2, capturedArgs["value"]);
        Assert.Equal(1.60934, capturedArgs["factor"]);
    }

    [Fact]
    public async Task GetSkillsAsync_ScriptDirectoriesWithNestedPath_DiscoversScriptsAsync()
    {
        // Arrange — ScriptDirectories configured with a multi-segment relative path (f1/f2/f3)
        string skillDir = CreateSkillDir(this._testRoot, "nested-script-skill", "Nested script directory", "Body.");
        CreateFile(skillDir, "f1/f2/f3/run.py", "print('nested')");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ScriptDirectories = ["f1/f2/f3"] });

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert — script file inside the deeply nested directory is discovered
        Assert.Single(skills);
        Assert.Single(skills[0].Scripts!);
        Assert.Equal("f1/f2/f3/run.py", skills[0].Scripts![0].Name);
    }

    [Theory]
    [InlineData("./scripts")]
    [InlineData("./scripts/f1")]
    [InlineData("./scripts/f1", "./f2")]
    public async Task GetSkillsAsync_ScriptDirectoryWithDotSlashPrefix_DiscoversScriptsAsync(params string[] directories)
    {
        // Arrange — "./"-prefixed directories are equivalent to their counterparts without the prefix;
        // the leading "./" is transparently normalized by Path.GetFullPath during file enumeration.
        string skillDir = CreateSkillDir(this._testRoot, "dotslash-script-skill", "Dot-slash prefix", "Body.");
        foreach (string directory in directories)
        {
            string directoryWithoutDotSlash = directory.Substring(2); // strip "./"
            CreateFile(skillDir, $"{directoryWithoutDotSlash}/run.py", "print('dotslash')");
        }

        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ScriptDirectories = directories });

        // Act
        var skills = await source.GetSkillsAsync(CancellationToken.None);

        // Assert — scripts are discovered with names identical to using directories without "./"
        Assert.Single(skills);
        Assert.Equal(directories.Length, skills[0].Scripts!.Count);
        foreach (string directory in directories)
        {
            string expectedName = $"{directory.Substring(2)}/run.py";
            Assert.Contains(skills[0].Scripts!, s => s.Name == expectedName);
        }
    }

    private static string CreateSkillDir(string root, string name, string description, string body)
    {
        string skillDir = Path.Combine(root, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {name}\ndescription: {description}\n---\n{body}");
        return skillDir;
    }

    private static void CreateSkillWithScript(string root, string name, string description, string body, string scriptRelativePath, string scriptContent)
    {
        string skillDir = CreateSkillDir(root, name, description, body);
        CreateFile(skillDir, scriptRelativePath, scriptContent);
    }

    private static void CreateFile(string root, string relativePath, string content)
    {
        string fullPath = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        File.WriteAllText(fullPath, content);
    }
}
