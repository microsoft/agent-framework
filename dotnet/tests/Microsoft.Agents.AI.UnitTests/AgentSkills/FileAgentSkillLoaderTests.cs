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
    [InlineData("consecutive--hyphens")]
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
        string dir1 = Path.Combine(this._testRoot, "dupe");
        string dir2 = Path.Combine(this._testRoot, "subdir");
        Directory.CreateDirectory(dir1);
        Directory.CreateDirectory(dir2);

        // Create a nested duplicate: subdir/dupe/SKILL.md
        string nestedDir = Path.Combine(dir2, "dupe");
        Directory.CreateDirectory(nestedDir);
        File.WriteAllText(
            Path.Combine(dir1, "SKILL.md"),
            "---\nname: dupe\ndescription: First\n---\nFirst body.");
        File.WriteAllText(
            Path.Combine(nestedDir, "SKILL.md"),
            "---\nname: dupe\ndescription: Second\n---\nSecond body.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert – filesystem enumeration order is not guaranteed, so we only
        // verify that exactly one of the two duplicates was kept.
        Assert.Single(skills);
        string desc = skills["dupe"].Frontmatter.Description;
        Assert.True(desc == "First" || desc == "Second", $"Unexpected description: {desc}");
    }

    [Fact]
    public void DiscoverAndLoadSkills_NameMismatchesDirectory_ExcludesSkill()
    {
        // Arrange — directory name differs from the frontmatter name
        _ = this.CreateSkillDirectoryWithRawContent(
            "wrong-dir-name",
            "---\nname: actual-skill-name\ndescription: A skill\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public void DiscoverAndLoadSkills_FilesWithMatchingExtensions_DiscoveredAsResources()
    {
        // Arrange — create resource files in the skill directory
        string skillDir = Path.Combine(this._testRoot, "resource-skill");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "FAQ.md"), "FAQ content");
        File.WriteAllText(Path.Combine(refsDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: resource-skill\ndescription: Has resources\n---\nSee docs for details.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        var skill = skills["resource-skill"];
        Assert.Equal(2, skill.ResourceNames.Count);
        Assert.Contains(skill.ResourceNames, r => r.Equals("refs/FAQ.md", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(skill.ResourceNames, r => r.Equals("refs/data.json", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void DiscoverAndLoadSkills_FilesWithNonMatchingExtensions_NotDiscovered()
    {
        // Arrange — create a file with an extension not in the default list
        string skillDir = Path.Combine(this._testRoot, "ext-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "image.png"), "fake image");
        File.WriteAllText(Path.Combine(skillDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: ext-skill\ndescription: Extension test\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        var skill = skills["ext-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Equal("data.json", skill.ResourceNames[0]);
    }

    [Fact]
    public void DiscoverAndLoadSkills_SkillMdFile_NotIncludedAsResource()
    {
        // Arrange — the SKILL.md file itself should not be in the resource list
        string skillDir = Path.Combine(this._testRoot, "selfref-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "notes.md"), "notes");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: selfref-skill\ndescription: Self ref test\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        var skill = skills["selfref-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Equal("notes.md", skill.ResourceNames[0]);
    }

    [Fact]
    public void DiscoverAndLoadSkills_NestedResourceFiles_Discovered()
    {
        // Arrange — resource files in nested subdirectories
        string skillDir = Path.Combine(this._testRoot, "nested-res-skill");
        string deepDir = Path.Combine(skillDir, "level1", "level2");
        Directory.CreateDirectory(deepDir);
        File.WriteAllText(Path.Combine(deepDir, "deep.md"), "deep content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: nested-res-skill\ndescription: Nested resources\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        var skill = skills["nested-res-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Contains(skill.ResourceNames, r => r.Equals("level1/level2/deep.md", StringComparison.OrdinalIgnoreCase));
    }

    private static readonly string[] s_customExtensions = new[] { ".custom" };
    private static readonly string[] s_validExtensions = new[] { ".md", ".json", ".custom" };
    private static readonly string[] s_mixedValidInvalidExtensions = new[] { ".md", "json" };

    [Fact]
    public void DiscoverAndLoadSkills_CustomResourceExtensions_UsedForDiscovery()
    {
        // Arrange — use a loader with custom extensions
        var customLoader = new FileAgentSkillLoader(NullLogger.Instance, s_customExtensions);
        string skillDir = Path.Combine(this._testRoot, "custom-ext-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "data.custom"), "custom data");
        File.WriteAllText(Path.Combine(skillDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: custom-ext-skill\ndescription: Custom extensions\n---\nBody.");

        // Act
        var skills = customLoader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert — only .custom files should be discovered, not .json
        Assert.Single(skills);
        var skill = skills["custom-ext-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Equal("data.custom", skill.ResourceNames[0]);
    }

    [Theory]
    [InlineData("txt")]
    [InlineData("")]
    [InlineData(" ")]
    public void Constructor_InvalidExtension_ThrowsArgumentException(string badExtension)
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new FileAgentSkillLoader(NullLogger.Instance, new[] { badExtension }));
    }

    [Fact]
    public void Constructor_NullExtensions_UsesDefaults()
    {
        // Arrange & Act
        var loader = new FileAgentSkillLoader(NullLogger.Instance, null);
        string skillDir = this.CreateSkillDirectory("null-ext", "A skill", "Body.");
        File.WriteAllText(Path.Combine(skillDir, "notes.md"), "notes");

        // Assert — default extensions include .md
        var skills = loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        Assert.Single(skills["null-ext"].ResourceNames);
    }

    [Fact]
    public void Constructor_ValidExtensions_DoesNotThrow()
    {
        // Arrange & Act & Assert — should not throw
        var loader = new FileAgentSkillLoader(NullLogger.Instance, s_validExtensions);
        Assert.NotNull(loader);
    }

    [Fact]
    public void Constructor_MixOfValidAndInvalidExtensions_ThrowsArgumentException()
    {
        // Arrange & Act & Assert — one bad extension in the list should cause failure
        Assert.Throws<ArgumentException>(() => new FileAgentSkillLoader(NullLogger.Instance, s_mixedValidInvalidExtensions));
    }

    [Fact]
    public void DiscoverAndLoadSkills_ResourceInSkillRoot_Discovered()
    {
        // Arrange — resource file directly in the skill directory (not in a subdirectory)
        string skillDir = Path.Combine(this._testRoot, "root-resource-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "guide.md"), "guide content");
        File.WriteAllText(Path.Combine(skillDir, "config.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: root-resource-skill\ndescription: Root resources\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert — both root-level resource files should be discovered
        Assert.Single(skills);
        var skill = skills["root-resource-skill"];
        Assert.Equal(2, skill.ResourceNames.Count);
        Assert.Contains(skill.ResourceNames, r => r.Equals("guide.md", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(skill.ResourceNames, r => r.Equals("config.json", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void DiscoverAndLoadSkills_NoResourceFiles_ReturnsEmptyResourceNames()
    {
        // Arrange — skill with no resource files
        _ = this.CreateSkillDirectory("no-resources", "A skill", "No resources here.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.Empty(skills["no-resources"].ResourceNames);
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
        // Arrange — create a skill with a resource file discovered from the directory
        string skillDir = this.CreateSkillDirectory("read-skill", "A skill", "See docs for details.");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "Document content here.");
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
        string skillDir = this.CreateSkillDirectory("traverse-read", "A skill", "See docs.");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "legit");
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
    public async Task ReadSkillResourceAsync_DotSlashPrefix_MatchesNormalizedResourceAsync()
    {
        // Arrange — skill loaded with bare path, caller uses ./ prefix
        string skillDir = this.CreateSkillDirectory("dotslash-read", "A skill", "See docs.");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "Document content.");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["dotslash-read"];

        // Act — caller passes ./refs/doc.md which should match refs/doc.md
        string content = await this._loader.ReadSkillResourceAsync(skill, "./refs/doc.md");

        // Assert
        Assert.Equal("Document content.", content);
    }

    [Fact]
    public async Task ReadSkillResourceAsync_BackslashSeparator_MatchesNormalizedResourceAsync()
    {
        // Arrange — skill loaded with forward-slash path, caller uses backslashes
        string skillDir = this.CreateSkillDirectory("backslash-read", "A skill", "See docs.");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "Backslash content.");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["backslash-read"];

        // Act — caller passes refs\doc.md which should match refs/doc.md
        string content = await this._loader.ReadSkillResourceAsync(skill, "refs\\doc.md");

        // Assert
        Assert.Equal("Backslash content.", content);
    }

    [Fact]
    public async Task ReadSkillResourceAsync_DotSlashWithBackslash_MatchesNormalizedResourceAsync()
    {
        // Arrange — skill loaded with forward-slash path, caller uses .\ prefix with backslashes
        string skillDir = this.CreateSkillDirectory("mixed-sep-read", "A skill", "See docs.");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "Mixed separator content.");
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });
        var skill = skills["mixed-sep-read"];

        // Act — caller passes .\refs\doc.md which should match refs/doc.md
        string content = await this._loader.ReadSkillResourceAsync(skill, ".\\refs\\doc.md");

        // Assert
        Assert.Equal("Mixed separator content.", content);
    }

#if NET
    [Fact]
    public void DiscoverAndLoadSkills_SymlinkInPath_SkipsSymlinkedResources()
    {
        // Arrange — a "refs" subdirectory is a symlink pointing outside the skill directory
        string skillDir = Path.Combine(this._testRoot, "symlink-escape-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "legit.md"), "legit content");

        string outsideDir = Path.Combine(this._testRoot, "outside");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "secret.md"), "secret content");

        string refsLink = Path.Combine(skillDir, "refs");
        try
        {
            Directory.CreateSymbolicLink(refsLink, outsideDir);
        }
        catch (IOException)
        {
            // Symlink creation requires elevation on some platforms; skip gracefully.
            return;
        }

        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: symlink-escape-skill\ndescription: Symlinked directory escape\n---\nBody.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert — skill should still load, but symlinked resources should be excluded
        Assert.True(skills.ContainsKey("symlink-escape-skill"));
        var skill = skills["symlink-escape-skill"];
        Assert.Single(skill.ResourceNames);
        Assert.Equal("legit.md", skill.ResourceNames[0]);
    }

    private static readonly string[] s_symlinkResource = ["refs/data.md"];

    [Fact]
    public async Task ReadSkillResourceAsync_SymlinkInPath_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange — build a skill with a symlinked subdirectory
        string skillDir = Path.Combine(this._testRoot, "symlink-read-skill");
        string refsDir = Path.Combine(skillDir, "refs");
        Directory.CreateDirectory(skillDir);

        string outsideDir = Path.Combine(this._testRoot, "outside-read");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "data.md"), "external data");

        try
        {
            Directory.CreateSymbolicLink(refsDir, outsideDir);
        }
        catch (IOException)
        {
            // Symlink creation requires elevation on some platforms; skip gracefully.
            return;
        }

        // Manually construct a skill that bypasses discovery validation
        var frontmatter = new SkillFrontmatter("symlink-read-skill", "A skill");
        var skill = new FileAgentSkill(
            frontmatter: frontmatter,
            body: "See [doc](refs/data.md).",
            sourcePath: skillDir,
            resourceNames: s_symlinkResource);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => this._loader.ReadSkillResourceAsync(skill, "refs/data.md"));
    }
#endif

    [Fact]
    public void DiscoverAndLoadSkills_FileWithUtf8Bom_ParsesSuccessfully()
    {
        // Arrange — prepend a UTF-8 BOM (\uFEFF) before the frontmatter
        _ = this.CreateSkillDirectoryWithRawContent(
            "bom-skill",
            "\uFEFF---\nname: bom-skill\ndescription: Skill with BOM\n---\nBody content.");

        // Act
        var skills = this._loader.DiscoverAndLoadSkills(new[] { this._testRoot });

        // Assert
        Assert.Single(skills);
        Assert.True(skills.ContainsKey("bom-skill"));
        Assert.Equal("Skill with BOM", skills["bom-skill"].Frontmatter.Description);
        Assert.Equal("Body content.", skills["bom-skill"].Body);
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

    private string CreateSkillDirectoryWithRawContent(string directoryName, string rawContent)
    {
        string skillDir = Path.Combine(this._testRoot, directoryName);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "SKILL.md"), rawContent);
        return skillDir;
    }
}
