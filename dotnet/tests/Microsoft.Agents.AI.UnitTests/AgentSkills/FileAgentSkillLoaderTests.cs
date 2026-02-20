// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for the <see cref="FileAgentSkillLoader"/> class.
/// </summary>
public sealed class FileAgentSkillLoaderTests : IDisposable
{
    private static readonly string[] s_traversalResource = new[] { "../secret.txt" };

    private readonly string _testRoot;
    private readonly FileAgentSkillLoader _loader;

    public FileAgentSkillLoaderTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "agent-skills-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._testRoot);
        this._loader = new FileAgentSkillLoader(NullLogger.Instance);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._testRoot))
        {
            Directory.Delete(this._testRoot, recursive: true);
        }
    }

    [Fact]
    public void DiscoverAndLoadSkills_ValidSkill_ReturnsSkill()
    {
        // Arrange
        _ = this.CreateSkillDirectory("my-skill", "A test skill", "Use this skill to do things.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.True(skills.ContainsKey("my-skill"));
        Assert.Equal("A test skill", skills["my-skill"].Frontmatter.Description);
        Assert.Equal("Use this skill to do things.", skills["my-skill"].Body);
    }

    [Fact]
    public void DiscoverAndLoadSkills_QuotedFrontmatterValues_ParsesCorrectly()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "quoted-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: 'quoted-skill'\ndescription: \"A quoted description\"\n---\nBody text.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.Equal("quoted-skill", skills["quoted-skill"].Frontmatter.Name);
        Assert.Equal("A quoted description", skills["quoted-skill"].Frontmatter.Description);
    }

    [Fact]
    public void DiscoverAndLoadSkills_MissingFrontmatter_ExcludesSkill()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "bad-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "SKILL.md"), "No frontmatter here.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_MissingNameField_ExcludesSkill()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "no-name");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\ndescription: A skill without a name\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_MissingDescriptionField_ExcludesSkill()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "no-desc");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: no-desc\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Theory]
    [InlineData("BadName")]
    [InlineData("-leading-hyphen")]
    [InlineData("trailing-hyphen-")]
    [InlineData("has spaces")]
    public void DiscoverAndLoadSkills_InvalidName_ExcludesSkill(string invalidName)
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "invalid-name-test");
        if (Directory.Exists(skillDir))
        {
            Directory.Delete(skillDir, recursive: true);
        }

        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {invalidName}\ndescription: A skill\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_DuplicateNames_KeepsFirstOnly()
    {
        // Arrange
        string dir1 = Path.Combine(this._testRoot, "skill-a");
        string dir2 = Path.Combine(this._testRoot, "skill-b");
        Directory.CreateDirectory(dir1);
        Directory.CreateDirectory(dir2);
        File.WriteAllText(
            Path.Combine(dir1, "SKILL.md"),
            "---\nname: dupe\ndescription: First\n---\nFirst body.");
        File.WriteAllText(
            Path.Combine(dir2, "SKILL.md"),
            "---\nname: dupe\ndescription: Second\n---\nSecond body.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.Equal("First", skills["dupe"].Frontmatter.Description);
    }

    [Fact]
    public void DiscoverAndLoadSkills_WithValidResourceLinks_ExtractsResourceNames()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "resource-skill");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "FAQ.md"), "FAQ content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: resource-skill\ndescription: Has resources\n---\nSee [FAQ](refs/FAQ.md) for details.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        var skill = skills["resource-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Equal("refs/FAQ.md", skill.ResourceNames[0]);
    }

    [Fact]
    public void DiscoverAndLoadSkills_PathTraversal_ExcludesSkill()
    {
        // Arrange — resource links outside the skill directory
        string skillDir = Path.Combine(this._testRoot, "traversal-skill");
        Directory.CreateDirectory(skillDir);

        // Create a file outside the skill dir that the traversal would resolve to
        File.WriteAllText(Path.Combine(this._testRoot, "secret.txt"), "secret");

        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: traversal-skill\ndescription: Traversal attempt\n---\nSee [doc](../secret.txt).");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_EmptyPaths_ReturnsEmptyDictionary()
    {
        // Act
        var skills = this._loader.DiscoverAndLoadSkills(Enumerable.Empty<string>());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_NonExistentPath_ReturnsEmptyDictionary()
    {
        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { Path.Combine(this._testRoot, "does-not-exist") });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_NestedSkillDirectory_DiscoveredWithinDepthLimit()
    {
        // Arrange — nested 1 level deep (MaxSearchDepth = 2, so depth 0 = testRoot, depth 1 = level1)
        string nestedDir = Path.Combine(this._testRoot, "level1", "nested-skill");
        Directory.CreateDirectory(nestedDir);
        File.WriteAllText(
            Path.Combine(nestedDir, "SKILL.md"),
            "---\nname: nested-skill\ndescription: Nested\n---\nNested body.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.True(skills.ContainsKey("nested-skill"));
    }

    [Fact]
    public async Task ReadSkillResourceAsync_ValidResource_ReturnsContentAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithResource("read-skill", "A skill", "See [doc](refs/doc.md).", "refs/doc.md", "Document content here.");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["read-skill"];

        // Act
        string content = await this._loader.ReadSkillResourceAsync(skill, "refs/doc.md");

        // Assert
        Assert.Equal("Document content here.", content);
    }

    [Fact]
    public async Task ReadSkillResourceAsync_UnregisteredResource_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        string skillDir = this.CreateSkillDirectory("simple-skill", "A skill", "No resources.");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["simple-skill"];

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => this._loader.ReadSkillResourceAsync(skill, "unknown.md"));
    }

    [Fact]
    public async Task ReadSkillResourceAsync_PathTraversal_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange — skill with a legitimate resource, then try to read a traversal path at read time
        _ = this.CreateSkillDirectoryWithResource("traverse-read", "A skill", "See [doc](refs/doc.md).", "refs/doc.md", "legit");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["traverse-read"];

        // Manually construct a skill with the traversal resource in its list to bypass discovery validation
        var tampered = new FileAgentSkill(
            skill.Frontmatter,
            skill.Body,
            skill.SourcePath,
            s_traversalResource);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => this._loader.ReadSkillResourceAsync(tampered, "../secret.txt"));
    }

    [Fact]
    public void DiscoverAndLoadSkills_NameExceedsMaxLength_ExcludesSkill()
    {
        // Arrange — name longer than 64 characters
        string longName = new('a', 65);
        string skillDir = Path.Combine(this._testRoot, "long-name");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {longName}\ndescription: A skill\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_DescriptionExceedsMaxLength_ExcludesSkill()
    {
        // Arrange — description longer than 1024 characters
        string longDesc = new('x', 1025);
        string skillDir = Path.Combine(this._testRoot, "long-desc");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: long-desc\ndescription: {longDesc}\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_DuplicateResourceLinks_DeduplicatesResources()
    {
        // Arrange — body references the same resource twice
        string skillDir = Path.Combine(this._testRoot, "dedup-skill");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: dedup-skill\ndescription: Dedup test\n---\nSee [doc](refs/doc.md) and [again](refs/doc.md).");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.Single(skills["dedup-skill"].ResourceNames);
    }

    private string CreateSkillDirectory(string name, string description, string body)
    {
        string skillDir = Path.Combine(this._testRoot, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {name}\ndescription: {description}\n---\n{body}");
        return skillDir;
    }

    private string CreateSkillDirectoryWithResource(string name, string description, string body, string resourceRelativePath, string resourceContent)
    {
        string skillDir = this.CreateSkillDirectory(name, description, body);
        string resourcePath = Path.Combine(skillDir, resourceRelativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(resourcePath)!);
        File.WriteAllText(resourcePath, resourceContent);
        return skillDir;
    }
}
