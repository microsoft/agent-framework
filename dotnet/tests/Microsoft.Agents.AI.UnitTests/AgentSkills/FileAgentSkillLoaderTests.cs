// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for the <see cref="AgentFileSkillsSource"/> skill discovery and parsing logic.
/// </summary>
public sealed class FileAgentSkillLoaderTests : IDisposable
{
    private static readonly string[] s_customExtensions = [".custom"];
    private static readonly string[] s_validExtensions = [".md", ".json", ".custom"];
    private static readonly string[] s_mixedValidInvalidExtensions = [".md", "json"];
    private static readonly AgentFileSkillScriptRunner s_noOpExecutor = (skill, script, args, ct) => Task.FromResult<object?>(null);

    private readonly string _testRoot;

    public FileAgentSkillLoaderTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "agent-skills-tests-" + Guid.NewGuid().ToString("N"));
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
    public async Task GetSkillsAsync_ValidSkill_ReturnsSkillAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectory("my-skill", "A test skill", "Use this skill to do things.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("my-skill", skills[0].Frontmatter.Name);
        Assert.Equal("A test skill", skills[0].Frontmatter.Description);
    }

    [Fact]
    public async Task GetSkillsAsync_QuotedFrontmatterValues_ParsesCorrectlyAsync()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "quoted-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: 'quoted-skill'\ndescription: \"A quoted description\"\n---\nBody text.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("quoted-skill", skills[0].Frontmatter.Name);
        Assert.Equal("A quoted description", skills[0].Frontmatter.Description);
    }

    [Fact]
    public async Task GetSkillsAsync_MissingFrontmatter_ExcludesSkillAsync()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "bad-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "SKILL.md"), "No frontmatter here.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_MissingNameField_ExcludesSkillAsync()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "no-name");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\ndescription: A skill without a name\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_MissingDescriptionField_ExcludesSkillAsync()
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, "no-desc");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: no-desc\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Theory]
    [InlineData("BadName")]
    [InlineData("-leading-hyphen")]
    [InlineData("trailing-hyphen-")]
    [InlineData("has spaces")]
    [InlineData("consecutive--hyphens")]
    public async Task GetSkillsAsync_InvalidName_ExcludesSkillAsync(string invalidName)
    {
        // Arrange
        string skillDir = Path.Combine(this._testRoot, invalidName);
        if (Directory.Exists(skillDir))
        {
            Directory.Delete(skillDir, recursive: true);
        }

        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {invalidName}\ndescription: A skill\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_DuplicateNames_KeepsFirstOnlyAsync()
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
        var fileSource = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var source = new DeduplicatingAgentSkillsSource(fileSource);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert – filesystem enumeration order is not guaranteed, so we only
        // verify that exactly one of the two duplicates was kept.
        Assert.Single(skills);
        string desc = skills[0].Frontmatter.Description;
        Assert.True(desc == "First" || desc == "Second", $"Unexpected description: {desc}");
    }

    [Fact]
    public async Task GetSkillsAsync_NameMismatchesDirectory_ExcludesSkillAsync()
    {
        // Arrange — directory name differs from the frontmatter name
        _ = this.CreateSkillDirectoryWithRawContent(
            "wrong-dir-name",
            "---\nname: actual-skill-name\ndescription: A skill\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_FilesWithMatchingExtensions_DiscoveredAsResourcesAsync()
    {
        // Arrange — create resource files in spec-defined subdirectories
        string skillDir = Path.Combine(this._testRoot, "resource-skill");
        string refsDir = Path.Combine(skillDir, "references");
        string assetsDir = Path.Combine(skillDir, "assets");
        Directory.CreateDirectory(refsDir);
        Directory.CreateDirectory(assetsDir);
        File.WriteAllText(Path.Combine(refsDir, "FAQ.md"), "FAQ content");
        File.WriteAllText(Path.Combine(assetsDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: resource-skill\ndescription: Has resources\n---\nSee docs for details.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Equal(2, skill.Resources!.Count);
        Assert.Contains(skill.Resources!, r => r.Name.Equals("references/FAQ.md", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(skill.Resources!, r => r.Name.Equals("assets/data.json", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task GetSkillsAsync_FilesWithNonMatchingExtensions_NotDiscoveredAsync()
    {
        // Arrange — create a file with an extension not in the default list inside a spec directory
        string skillDir = Path.Combine(this._testRoot, "ext-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "image.png"), "fake image");
        File.WriteAllText(Path.Combine(refsDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: ext-skill\ndescription: Extension test\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Equal("references/data.json", skill.Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SkillMdFile_NotIncludedAsResourceAsync()
    {
        // Arrange — the SKILL.md file itself should not be in the resource list
        string skillDir = Path.Combine(this._testRoot, "selfref-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "notes.md"), "notes");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: selfref-skill\ndescription: Self ref test\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Equal("references/notes.md", skill.Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_NestedResourceFiles_DiscoveredAsync()
    {
        // Arrange — resource files directly in references/ are discovered; subdirectories are not scanned
        string skillDir = Path.Combine(this._testRoot, "nested-res-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "top.md"), "top content");
        string deepDir = Path.Combine(refsDir, "level1", "level2");
        Directory.CreateDirectory(deepDir);
        File.WriteAllText(Path.Combine(deepDir, "deep.md"), "deep content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: nested-res-skill\ndescription: Nested resources\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only the file directly in references/ is discovered; the nested file is not
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Contains(skill.Resources!, r => r.Name.Equals("references/top.md", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain(skill.Resources!, r => r.Name.Contains("deep.md", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task GetSkillsAsync_CustomResourceExtensions_UsedForDiscoveryAsync()
    {
        // Arrange — use a source with custom extensions; files placed in spec directory
        string skillDir = Path.Combine(this._testRoot, "custom-ext-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "data.custom"), "custom data");
        File.WriteAllText(Path.Combine(refsDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: custom-ext-skill\ndescription: Custom extensions\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { AllowedResourceExtensions = s_customExtensions });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only .custom files should be discovered, not .json
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Equal("references/data.custom", skill.Resources![0].Name);
    }

    [Theory]
    [InlineData("txt")]
    [InlineData("")]
    [InlineData(" ")]
    public void Constructor_InvalidExtension_ThrowsArgumentException(string badExtension)
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { AllowedResourceExtensions = new string[] { badExtension } }));
    }

    [Fact]
    public async Task Constructor_NullExtensions_UsesDefaultsAsync()
    {
        // Arrange & Act
        string skillDir = this.CreateSkillDirectory("null-ext", "A skill", "Body.");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "notes.md"), "notes");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Assert — default extensions include .md
        var skills = await source.GetSkillsAsync();
        Assert.Single(skills[0].Resources!);
    }

    [Fact]
    public void Constructor_ValidExtensions_DoesNotThrow()
    {
        // Arrange & Act & Assert — should not throw
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { AllowedResourceExtensions = s_validExtensions });
        Assert.NotNull(source);
    }

    [Fact]
    public void Constructor_MixOfValidAndInvalidExtensions_ThrowsArgumentException()
    {
        // Arrange & Act & Assert — one bad extension in the list should cause failure
        Assert.Throws<ArgumentException>(() => new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { AllowedResourceExtensions = s_mixedValidInvalidExtensions }));
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceInSkillRoot_NotDiscoveredByDefaultAsync()
    {
        // Arrange — resource files directly in the skill directory (not in a spec subdirectory)
        string skillDir = Path.Combine(this._testRoot, "root-resource-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "guide.md"), "guide content");
        File.WriteAllText(Path.Combine(skillDir, "config.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: root-resource-skill\ndescription: Root resources\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — root-level files are NOT discovered unless "." is in ResourceDirectories
        Assert.Single(skills);
        Assert.Empty(skills[0].Resources!);
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceInSkillRoot_DiscoveredWhenRootDirectoryConfiguredAsync()
    {
        // Arrange — "." in ResourceDirectories opts into root-level resource discovery
        string skillDir = Path.Combine(this._testRoot, "root-opt-in-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "guide.md"), "guide content");
        File.WriteAllText(Path.Combine(skillDir, "config.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: root-opt-in-skill\ndescription: Root opt-in\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["references", "assets", "."] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — both root-level resource files (and SKILL.md excluded) should be discovered
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Equal(2, skill.Resources!.Count);
        Assert.Contains(skill.Resources!, r => r.Name.Equals("guide.md", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(skill.Resources!, r => r.Name.Equals("config.json", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceInNonSpecDirectory_NotDiscoveredByDefaultAsync()
    {
        // Arrange — resource in a non-spec directory (neither references/ nor assets/)
        string skillDir = Path.Combine(this._testRoot, "non-spec-skill");
        string customDir = Path.Combine(skillDir, "docs");
        Directory.CreateDirectory(customDir);
        File.WriteAllText(Path.Combine(customDir, "readme.md"), "docs content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: non-spec-skill\ndescription: Non-spec directory\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — non-spec directories are not scanned by default
        Assert.Single(skills);
        Assert.Empty(skills[0].Resources!);
    }

    [Fact]
    public async Task GetSkillsAsync_CustomResourceDirectories_ReplacesDefaultsAsync()
    {
        // Arrange — custom ResourceDirectories replaces the spec defaults
        string skillDir = Path.Combine(this._testRoot, "custom-directory-skill");
        string customDir = Path.Combine(skillDir, "docs");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(customDir);
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(customDir, "readme.md"), "docs content");
        File.WriteAllText(Path.Combine(refsDir, "ref.md"), "ref content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: custom-directory-skill\ndescription: Custom directory\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["docs"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only docs/ is scanned; references/ is NOT scanned
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Equal("docs/readme.md", skill.Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_NoResourceFiles_ReturnsEmptyResourcesAsync()
    {
        // Arrange — skill with no resource files
        _ = this.CreateSkillDirectory("no-resources", "A skill", "No resources here.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Empty(skills[0].Resources!);
    }

    [Fact]
    public async Task GetSkillsAsync_EmptyPaths_ReturnsEmptyListAsync()
    {
        // Arrange
        var source = new AgentFileSkillsSource(Enumerable.Empty<string>(), s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_NonExistentPath_ReturnsEmptyListAsync()
    {
        // Arrange
        var source = new AgentFileSkillsSource(Path.Combine(this._testRoot, "does-not-exist"), s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_NestedSkillDirectory_DiscoveredWithinDepthLimitAsync()
    {
        // Arrange — nested 1 level deep (MaxSearchDepth = 2, so depth 0 = testRoot, depth 1 = level1)
        string nestedDir = Path.Combine(this._testRoot, "level1", "nested-skill");
        Directory.CreateDirectory(nestedDir);
        File.WriteAllText(
            Path.Combine(nestedDir, "SKILL.md"),
            "---\nname: nested-skill\ndescription: Nested\n---\nNested body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("nested-skill", skills[0].Frontmatter.Name);
    }

    [Fact]
    public async Task ReadSkillResourceAsync_ValidResource_ReturnsContentAsync()
    {
        // Arrange — create a skill with a resource file discovered from the references directory
        string skillDir = this.CreateSkillDirectory("read-skill", "A skill", "See docs for details.");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "doc.md"), "Document content here.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);
        var skills = await source.GetSkillsAsync();
        var resource = skills[0].Resources!.First(r => r.Name == "references/doc.md");

        // Act
        var content = await resource.ReadAsync();

        // Assert
        Assert.Equal("Document content here.", content);
    }

    [Fact]
    public async Task GetSkillsAsync_NameExceedsMaxLength_ExcludesSkillAsync()
    {
        // Arrange — name longer than 64 characters
        string longName = new('a', 65);
        string skillDir = Path.Combine(this._testRoot, "long-name");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: {longName}\ndescription: A skill\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_DescriptionExceedsMaxLength_ExcludesSkillAsync()
    {
        // Arrange — description longer than 1024 characters
        string longDesc = new('x', 1025);
        string skillDir = Path.Combine(this._testRoot, "long-desc");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            $"---\nname: long-desc\ndescription: {longDesc}\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Empty(skills);
    }

#if NET
    [Fact]
    public async Task GetSkillsAsync_SymlinkInPath_SkipsSymlinkedResourcesAsync()
    {
        // Arrange — references/ is a symlink pointing outside the skill directory;
        // a legitimate file lives in assets/ and should still be discovered.
        string skillDir = Path.Combine(this._testRoot, "symlink-escape-skill");
        string assetsDir = Path.Combine(skillDir, "assets");
        Directory.CreateDirectory(assetsDir);
        File.WriteAllText(Path.Combine(assetsDir, "legit.md"), "legit content");

        string outsideDir = Path.Combine(this._testRoot, "outside");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "secret.md"), "secret content");

        string refsLink = Path.Combine(skillDir, "references");
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
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — skill should still load, the symlinked references/ is skipped, assets/legit.md is found
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "symlink-escape-skill");
        Assert.NotNull(skill);
        Assert.Single(skill.Resources!);
        Assert.Equal("assets/legit.md", skill.Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SymlinkedResourceDirectory_SkipsWithoutEnumeratingAsync()
    {
        // Arrange — references/ is a symlink pointing outside the skill directory.
        // The directory-level check should skip it entirely (no file enumeration),
        // so even files with valid extensions in the target are not discovered.
        string skillDir = Path.Combine(this._testRoot, "symlink-directory-skip");
        string assetsDir = Path.Combine(skillDir, "assets");
        Directory.CreateDirectory(assetsDir);
        File.WriteAllText(Path.Combine(assetsDir, "legit.md"), "legit content");

        string outsideDir = Path.Combine(this._testRoot, "outside-resources");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "external.md"), "external content");
        File.WriteAllText(Path.Combine(outsideDir, "data.json"), "{}");

        string refsLink = Path.Combine(skillDir, "references");
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
            "---\nname: symlink-directory-skip\ndescription: Symlinked directory skip\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only assets/legit.md is found; the symlinked references/ directory is skipped entirely
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "symlink-directory-skip");
        Assert.NotNull(skill);
        Assert.Single(skill.Resources!);
        Assert.Equal("assets/legit.md", skill.Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SymlinkedScriptDirectory_SkipsWithoutEnumeratingAsync()
    {
        // Arrange — scripts/ is a symlink pointing outside the skill directory.
        // The directory-level check should skip it entirely.
        string skillDir = Path.Combine(this._testRoot, "symlink-script-skip");
        Directory.CreateDirectory(skillDir);

        string outsideDir = Path.Combine(this._testRoot, "outside-scripts");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "malicious.py"), "import os; os.system('rm -rf /')");

        string scriptsLink = Path.Combine(skillDir, "scripts");
        try
        {
            Directory.CreateSymbolicLink(scriptsLink, outsideDir);
        }
        catch (IOException)
        {
            return;
        }

        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: symlink-script-skip\ndescription: Symlinked script directory\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — skill loads but scripts from the symlinked directory are not discovered
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "symlink-script-skip");
        Assert.NotNull(skill);
        Assert.Empty(skill.Scripts!);
    }

    [Fact]
    public async Task GetSkillsAsync_SymlinkedIntermediateSegment_SkipsCustomDirectoryAsync()
    {
        // Arrange — custom resource directory "sub/resources" where "sub" is a symlink.
        // The directory-level HasSymlinkInPath check should detect the intermediate symlink.
        string skillDir = Path.Combine(this._testRoot, "symlink-intermediate");
        Directory.CreateDirectory(skillDir);

        string outsideDir = Path.Combine(this._testRoot, "outside-intermediate");
        string outsideResources = Path.Combine(outsideDir, "resources");
        Directory.CreateDirectory(outsideResources);
        File.WriteAllText(Path.Combine(outsideResources, "data.md"), "data");

        string subLink = Path.Combine(skillDir, "sub");
        try
        {
            Directory.CreateSymbolicLink(subLink, outsideDir);
        }
        catch (IOException)
        {
            return;
        }

        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: symlink-intermediate\ndescription: Intermediate symlink\n---\nBody.");
        var source = new AgentFileSkillsSource(
            this._testRoot,
            s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["sub/resources"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — the symlinked intermediate segment causes the directory to be skipped
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "symlink-intermediate");
        Assert.NotNull(skill);
        Assert.Empty(skill.Resources!);
    }
#endif

    [Fact]
    public async Task GetSkillsAsync_FileWithUtf8Bom_ParsesSuccessfullyAsync()
    {
        // Arrange — prepend a UTF-8 BOM (\uFEFF) before the frontmatter
        _ = this.CreateSkillDirectoryWithRawContent(
            "bom-skill",
            "\uFEFF---\nname: bom-skill\ndescription: Skill with BOM\n---\nBody content.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("bom-skill", skills[0].Frontmatter.Name);
        Assert.Equal("Skill with BOM", skills[0].Frontmatter.Description);
    }

    [Fact]
    public async Task GetSkillsAsync_LicenseField_ParsedCorrectlyAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithRawContent(
            "licensed-skill",
            "---\nname: licensed-skill\ndescription: A skill with license\nlicense: MIT\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("MIT", skills[0].Frontmatter.License);
    }

    [Fact]
    public async Task GetSkillsAsync_CompatibilityField_ParsedCorrectlyAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithRawContent(
            "compat-skill",
            "---\nname: compat-skill\ndescription: A skill with compatibility\ncompatibility: Requires Node.js 18+\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("Requires Node.js 18+", skills[0].Frontmatter.Compatibility);
    }

    [Fact]
    public async Task GetSkillsAsync_AllowedToolsField_ParsedCorrectlyAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithRawContent(
            "tools-skill",
            "---\nname: tools-skill\ndescription: A skill with tools\nallowed-tools: grep glob bash\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.Equal("grep glob bash", skills[0].Frontmatter.AllowedTools);
    }

    [Fact]
    public async Task GetSkillsAsync_MetadataField_ParsedCorrectlyAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithRawContent(
            "meta-skill",
            "---\nname: meta-skill\ndescription: A skill with metadata\nmetadata:\n  author: test-user\n  version: 1.0\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.NotNull(skills[0].Frontmatter.Metadata);
        Assert.Equal("test-user", skills[0].Frontmatter.Metadata!["author"]?.ToString());
        Assert.Equal("1.0", skills[0].Frontmatter.Metadata!["version"]?.ToString());
    }

    [Fact]
    public async Task GetSkillsAsync_MetadataWithQuotedValues_ParsedCorrectlyAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectoryWithRawContent(
            "quoted-meta",
            "---\nname: quoted-meta\ndescription: Metadata with quotes\nmetadata:\n  key1: 'single quoted'\n  key2: \"double quoted\"\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        Assert.NotNull(skills[0].Frontmatter.Metadata);
        Assert.Equal("single quoted", skills[0].Frontmatter.Metadata!["key1"]?.ToString());
        Assert.Equal("double quoted", skills[0].Frontmatter.Metadata!["key2"]?.ToString());
    }

    [Fact]
    public async Task GetSkillsAsync_AllOptionalFields_ParsedCorrectlyAsync()
    {
        // Arrange
        string content = string.Join(
            "\n",
            "---",
            "name: full-skill",
            "description: A skill with all fields",
            "license: Apache-2.0",
            "compatibility: Requires Python 3.10+",
            "allowed-tools: grep glob view",
            "metadata:",
            "  org: contoso",
            "  tier: premium",
            "---",
            "Full body content.");
        _ = this.CreateSkillDirectoryWithRawContent("full-skill", content);
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var fm = skills[0].Frontmatter;
        Assert.Equal("full-skill", fm.Name);
        Assert.Equal("A skill with all fields", fm.Description);
        Assert.Equal("Apache-2.0", fm.License);
        Assert.Equal("Requires Python 3.10+", fm.Compatibility);
        Assert.Equal("grep glob view", fm.AllowedTools);
        Assert.NotNull(fm.Metadata);
        Assert.Equal("contoso", fm.Metadata!["org"]?.ToString());
        Assert.Equal("premium", fm.Metadata!["tier"]?.ToString());
    }

    [Fact]
    public async Task GetSkillsAsync_NoOptionalFields_DefaultsToNullAsync()
    {
        // Arrange
        _ = this.CreateSkillDirectory("basic-skill", "A basic skill", "Body.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert
        Assert.Single(skills);
        var fm = skills[0].Frontmatter;
        Assert.Null(fm.License);
        Assert.Null(fm.Compatibility);
        Assert.Null(fm.AllowedTools);
        Assert.Null(fm.Metadata);
    }

    [Theory]
    [InlineData("..")]
    [InlineData("../escape")]
    [InlineData("sub/../escape")]
    [InlineData("/absolute")]
    [InlineData("\\absolute")]
    public void Constructor_InvalidDirectoryName_SkipsInvalidDirectories(string badDirectory)
    {
        // Arrange & Act — invalid directories are skipped with a warning rather than throwing
        var source1 = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { ScriptDirectories = [badDirectory] });
        var source2 = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { ResourceDirectories = [badDirectory] });

        // Assert
        Assert.NotNull(source1);
        Assert.NotNull(source2);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_NullOrWhitespaceDirectoryName_ThrowsArgumentException(string? badDirectory)
    {
        // Arrange & Act & Assert — null/whitespace is a contract violation, not a config error
        Assert.Throws<ArgumentException>(() => new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { ScriptDirectories = [badDirectory!] }));
        Assert.Throws<ArgumentException>(() => new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { ResourceDirectories = [badDirectory!] }));
    }

    [Theory]
    [InlineData("scripts")]
    [InlineData("my-scripts")]
    [InlineData("sub/directory")]
    [InlineData(".")]
    [InlineData("./scripts")]
    [InlineData("./scripts/f1")]
    [InlineData("my..scripts")]
    public void Constructor_ValidDirectoryName_DoesNotThrow(string validDirectory)
    {
        // Arrange & Act & Assert
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor, new AgentFileSkillsSourceOptions { ScriptDirectories = [validDirectory] });
        Assert.NotNull(source);
    }

    [Fact]
    public async Task GetSkillsAsync_DuplicateDirectoriesAfterNormalization_NoDuplicateResourcesAsync()
    {
        // Arrange — "references" and "./references" refer to the same directory;
        // after normalization they should be deduplicated so resources appear only once.
        string skillDir = Path.Combine(this._testRoot, "dedup-directory-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "FAQ.md"), "FAQ content");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: dedup-directory-skill\ndescription: Dedup test\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["references", "./references"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only one copy of the resource despite two equivalent directory entries
        Assert.Single(skills);
        Assert.Single(skills[0].Resources!);
        Assert.Equal("references/FAQ.md", skills[0].Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_TrailingSlashDirectoryNormalized_NoDuplicateResourcesAsync()
    {
        // Arrange — "references/" should be normalized to "references"
        string skillDir = Path.Combine(this._testRoot, "trailing-slash-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: trailing-slash-skill\ndescription: Trailing slash test\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["references", "references/"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — trailing slash variant deduplicated
        Assert.Single(skills);
        Assert.Single(skills[0].Resources!);
        Assert.Equal("references/data.json", skills[0].Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_BackslashDirectoryNormalized_NoDuplicateScriptsAsync()
    {
        // Arrange — ".\\scripts" should be normalized to "scripts"
        string skillDir = Path.Combine(this._testRoot, "backslash-skill");
        string scriptsDir = Path.Combine(skillDir, "scripts");
        Directory.CreateDirectory(scriptsDir);
        File.WriteAllText(Path.Combine(scriptsDir, "run.py"), "print('hello')");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: backslash-skill\ndescription: Backslash test\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ScriptDirectories = ["scripts", ".\\scripts"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — backslash variant deduplicated
        Assert.Single(skills);
        Assert.Single(skills[0].Scripts!);
        Assert.Equal("scripts/run.py", skills[0].Scripts![0].Name);
    }

    [Theory]
    [InlineData("./references")]
    [InlineData("./assets/docs")]
    public async Task GetSkillsAsync_ResourceDirectoryWithDotSlashPrefix_DiscoversResourcesAsync(string directory)
    {
        // Arrange — "./references" and "./assets/docs" are equivalent to "references" and "assets/docs";
        // the leading "./" is transparently normalized by Path.GetFullPath during file enumeration.
        string directoryWithoutDotSlash = directory.Substring(2); // strip "./"
        string skillDir = Path.Combine(this._testRoot, "dotslash-res-skill");
        string targetDir = Path.Combine(skillDir, directoryWithoutDotSlash.Replace('/', Path.DirectorySeparatorChar));
        Directory.CreateDirectory(targetDir);
        File.WriteAllText(Path.Combine(targetDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: dotslash-res-skill\ndescription: Dot-slash prefix\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = [directory] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — the resource is discovered with a name identical to using the directory without "./"
        Assert.Single(skills);
        Assert.Single(skills[0].Resources!);
        Assert.Equal($"{directoryWithoutDotSlash}/data.json", skills[0].Resources![0].Name);
    }

    [Fact]
    public async Task GetSkillsAsync_ResourceDirectoriesWithNestedPath_DiscoversResourcesAsync()
    {
        // Arrange — ResourceDirectories configured with a multi-segment relative path (f1/f2/f3)
        string skillDir = Path.Combine(this._testRoot, "nested-directory-skill");
        string nestedDir = Path.Combine(skillDir, "f1", "f2", "f3");
        Directory.CreateDirectory(nestedDir);
        File.WriteAllText(Path.Combine(nestedDir, "data.json"), "{}");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: nested-directory-skill\ndescription: Nested directory\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ResourceDirectories = ["f1/f2/f3"] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — resource file inside the deeply nested directory is discovered
        Assert.Single(skills);
        var skill = skills[0];
        Assert.Single(skill.Resources!);
        Assert.Equal("f1/f2/f3/data.json", skill.Resources![0].Name);
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

    [Theory]
    [InlineData("txt")]
    [InlineData("")]
    [InlineData(" ")]
    public void Constructor_InvalidScriptExtension_ThrowsArgumentException(string badExtension)
    {
        // Arrange & Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentFileSkillsSource(
            this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { AllowedScriptExtensions = new string[] { badExtension } }));
    }

    [Fact]
    public async Task GetSkillsAsync_SkillBeyondMaxDepth_NotDiscoveredAsync()
    {
        // Arrange — create a skill at depth 3 (exceeds MaxSearchDepth = 2)
        string deepDir = Path.Combine(this._testRoot, "l1", "l2", "l3", "deep-skill");
        Directory.CreateDirectory(deepDir);
        File.WriteAllText(
            Path.Combine(deepDir, "SKILL.md"),
            "---\nname: deep-skill\ndescription: Too deep\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — skill at depth 3 should not be discovered
        Assert.DoesNotContain(skills, s => s.Frontmatter.Name == "deep-skill");
    }

    [Fact]
    public async Task GetSkillsAsync_ScriptInSkillRoot_DiscoveredWhenRootDirectoryConfiguredAsync()
    {
        // Arrange — script file directly in the skill directory with ScriptDirectories = ["."]
        string skillDir = Path.Combine(this._testRoot, "root-script-skill");
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "run.py"), "print('hello')");
        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: root-script-skill\ndescription: Root script\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor,
            new AgentFileSkillsSourceOptions { ScriptDirectories = ["."] });

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — script at the skill root should be discovered
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "root-script-skill");
        Assert.NotNull(skill);
        Assert.Single(skill.Scripts!);
        Assert.Equal("run.py", skill.Scripts![0].Name);
    }

#if NET
    [Fact]
    public async Task GetSkillsAsync_SymlinkedFileInRealDirectory_SkipsSymlinkedFileAsync()
    {
        // Arrange — references/ is a real directory, but one file inside it is a symlink
        // pointing outside the skill directory. The per-file symlink check should skip it.
        string skillDir = Path.Combine(this._testRoot, "symlink-file-skill");
        string refsDir = Path.Combine(skillDir, "references");
        Directory.CreateDirectory(refsDir);
        File.WriteAllText(Path.Combine(refsDir, "legit.md"), "legit content");

        string outsideDir = Path.Combine(this._testRoot, "outside-file");
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "secret.md"), "secret content");

        string symlinkFile = Path.Combine(refsDir, "leak.md");
        try
        {
            File.CreateSymbolicLink(symlinkFile, Path.Combine(outsideDir, "secret.md"));
        }
        catch (IOException)
        {
            // Symlink creation requires elevation on some platforms; skip gracefully.
            return;
        }

        File.WriteAllText(
            Path.Combine(skillDir, "SKILL.md"),
            "---\nname: symlink-file-skill\ndescription: Symlinked file\n---\nBody.");
        var source = new AgentFileSkillsSource(this._testRoot, s_noOpExecutor);

        // Act
        var skills = await source.GetSkillsAsync();

        // Assert — only legit.md should be discovered; the symlinked leak.md is skipped
        var skill = skills.FirstOrDefault(s => s.Frontmatter.Name == "symlink-file-skill");
        Assert.NotNull(skill);
        Assert.Single(skill.Resources!);
        Assert.Equal("references/legit.md", skill.Resources![0].Name);
    }
#endif
}
