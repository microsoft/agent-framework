// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests that verify the Hosted-AgentSkills sample patterns: ZIP extraction with
/// zip-slip guard, skill name validation, and AgentSkillsProvider loading from
/// downloaded skill directories (the Foundry download → extract → wire-into-provider flow).
/// </summary>
public sealed class HostedAgentSkillsPatternTests : IDisposable
{
    private readonly string _testRoot;
    private readonly TestAIAgent _agent = new();

    public HostedAgentSkillsPatternTests()
    {
        this._testRoot = Path.Combine(Path.GetTempPath(), "hosted-skills-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._testRoot);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._testRoot))
        {
            Directory.Delete(this._testRoot, recursive: true);
        }
    }

    // ── ZIP extraction tests ──────────────────────────────────────────────────

    [Fact]
    public void SafeExtractZip_ValidArchive_ExtractsToDestination()
    {
        // Arrange
        string destDir = Path.Combine(this._testRoot, "valid-extract");
        Directory.CreateDirectory(destDir);
        byte[] zip = CreateZipWithEntry("SKILL.md", "---\nname: test\ndescription: Test\n---\nBody.");

        // Act
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        SafeExtractZip(archive, destDir);

        // Assert
        Assert.True(File.Exists(Path.Combine(destDir, "SKILL.md")));
        string content = File.ReadAllText(Path.Combine(destDir, "SKILL.md"));
        Assert.Contains("name: test", content);
    }

    [Fact]
    public void SafeExtractZip_ZipSlipAttempt_ThrowsInvalidOperationException()
    {
        // Arrange
        string destDir = Path.Combine(this._testRoot, "zipslip-test");
        Directory.CreateDirectory(destDir);
        byte[] zip = CreateZipWithEntry("../../../evil.txt", "malicious content");

        // Act & Assert
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        var ex = Assert.Throws<InvalidOperationException>(() => SafeExtractZip(archive, destDir));
        Assert.Contains("outside of", ex.Message);
    }

    [Fact]
    public void SafeExtractZip_SiblingPrefixAttack_ThrowsInvalidOperationException()
    {
        // Arrange — sibling path that starts with the dest dir name
        string destDir = Path.Combine(this._testRoot, "target");
        Directory.CreateDirectory(destDir);
        byte[] zip = CreateZipWithEntry("../target-evil/payload.txt", "exploit");

        // Act & Assert
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        var ex = Assert.Throws<InvalidOperationException>(() => SafeExtractZip(archive, destDir));
        Assert.Contains("outside of", ex.Message);
    }

    [Fact]
    public void SafeExtractZip_DirectoryEntry_CreatesDirectory()
    {
        // Arrange
        string destDir = Path.Combine(this._testRoot, "dir-entry");
        Directory.CreateDirectory(destDir);
        byte[] zip = CreateZipWithDirectoryEntry("subdir/");

        // Act
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        SafeExtractZip(archive, destDir);

        // Assert
        Assert.True(Directory.Exists(Path.Combine(destDir, "subdir")));
    }

    [Fact]
    public void SafeExtractZip_NestedFileWithinDestination_Extracts()
    {
        // Arrange — a legitimate nested entry must still pass the single containment gate
        string destDir = Path.Combine(this._testRoot, "nested-extract");
        Directory.CreateDirectory(destDir);
        byte[] zip = CreateZipWithEntry("docs/SKILL.md", "nested body");

        // Act
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        SafeExtractZip(archive, destDir);

        // Assert
        string extracted = Path.Combine(destDir, "docs", "SKILL.md");
        Assert.True(File.Exists(extracted));
        Assert.Equal("nested body", File.ReadAllText(extracted));
    }

    // ── Skill name validation tests ──────────────────────────────────────────

    [Theory]
    [InlineData("../escape")]
    [InlineData("path/traversal")]
    [InlineData("path\\traversal")]
    [InlineData("has.dots")]
    public void ValidateSkillName_InvalidNames_Rejected(string name)
    {
        // Act & Assert
        Assert.True(IsInvalidSkillName(name), $"Expected '{name}' to be rejected.");
    }

    [Theory]
    [InlineData("support-style")]
    [InlineData("escalation-policy")]
    [InlineData("my-skill-123")]
    public void ValidateSkillName_ValidNames_Accepted(string name)
    {
        // Act & Assert
        Assert.False(IsInvalidSkillName(name), $"Expected '{name}' to be accepted.");
    }

    // ── AgentSkillsProvider integration with downloaded skill directories ─────

    [Fact]
    public async Task AgentSkillsProvider_WithDownloadedSkills_AdvertisesAndLoadsAsync()
    {
        // Arrange — simulate the Foundry download + extract flow
        string downloadDir = Path.Combine(this._testRoot, "downloaded_skills");
        Directory.CreateDirectory(downloadDir);

        CreateDownloadedSkill(downloadDir, "support-style",
            "---\nname: support-style\ndescription: Contoso Outdoors customer-support tone and formatting guidelines.\n---\n\n# Contoso Outdoors Support Style\n\nYou are speaking on behalf of Contoso Outdoors.\n\n## Canary\n\nInclude STYLE-CANARY-3318.");
        CreateDownloadedSkill(downloadDir, "escalation-policy",
            "---\nname: escalation-policy\ndescription: When and how to escalate Contoso Outdoors customer-support tickets.\n---\n\n# Escalation Policy\n\nProvide ESC-CANARY-7742.");

        var provider = new AgentSkillsProvider(downloadDir, scriptRunner: null);
        var inputContext = new AIContext
        {
            Instructions = "You are a customer-support assistant for Contoso Outdoors."
        };
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);

        // Act
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — skills are advertised in instructions
        Assert.NotNull(result.Instructions);
        Assert.Contains("support-style", result.Instructions);
        Assert.Contains("escalation-policy", result.Instructions);
        Assert.Contains("Contoso Outdoors customer-support tone", result.Instructions);

        // Assert — load_skill tool is available
        Assert.NotNull(result.Tools);
        var toolNames = result.Tools!.Select(t => t.Name).ToList();
        Assert.Contains("load_skill", toolNames);
        // All tools are always included regardless of whether skills have resources or scripts
        Assert.Contains("read_skill_resource", toolNames);
        Assert.Contains("run_skill_script", toolNames);
    }

    [Fact]
    public async Task LoadSkill_ReturnsFullContentWithCanaryAsync()
    {
        // Arrange
        string downloadDir = Path.Combine(this._testRoot, "canary_skills");
        Directory.CreateDirectory(downloadDir);
        CreateDownloadedSkill(downloadDir, "support-style",
            "---\nname: support-style\ndescription: Contoso tone guidelines.\n---\n\nInclude STYLE-CANARY-3318 at the bottom.");

        var provider = new AgentSkillsProvider(downloadDir, scriptRunner: null);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;
        Assert.NotNull(loadSkillTool);

        // Act
        var content = await loadSkillTool!.InvokeAsync(
            new AIFunctionArguments(new System.Collections.Generic.Dictionary<string, object?> { ["skillName"] = "support-style" }));

        // Assert
        var text = content!.ToString()!;
        Assert.Contains("STYLE-CANARY-3318", text);
        Assert.Contains("name: support-style", text);
    }

    [Fact]
    public async Task LoadSkill_UnknownName_ReturnsErrorAsync()
    {
        // Arrange
        string downloadDir = Path.Combine(this._testRoot, "error_skills");
        Directory.CreateDirectory(downloadDir);
        CreateDownloadedSkill(downloadDir, "support-style",
            "---\nname: support-style\ndescription: Test\n---\nBody.");

        var provider = new AgentSkillsProvider(downloadDir, scriptRunner: null);
        var inputContext = new AIContext();
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, inputContext);
        var result = await provider.InvokingAsync(invokingContext, CancellationToken.None);

        var loadSkillTool = result.Tools!.First(t => t.Name == "load_skill") as AIFunction;

        // Act
        var content = await loadSkillTool!.InvokeAsync(
            new AIFunctionArguments(new System.Collections.Generic.Dictionary<string, object?> { ["skillName"] = "nonexistent-skill" }));

        // Assert
        var text = content!.ToString()!;
        Assert.Contains("Error", text);
        Assert.Contains("not found", text);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    /// <summary>
    /// Creates a downloaded skill directory with a SKILL.md file — simulating what
    /// the Foundry download + ZIP extract flow produces.
    /// </summary>
    private static void CreateDownloadedSkill(string parentDir, string name, string content)
    {
        string skillDir = Path.Combine(parentDir, name);
        Directory.CreateDirectory(skillDir);
        File.WriteAllText(Path.Combine(skillDir, "SKILL.md"), content);
    }

    /// <summary>
    /// Creates a ZIP archive in memory containing a single file entry.
    /// </summary>
    private static byte[] CreateZipWithEntry(string entryName, string content)
    {
        using var ms = new MemoryStream();
        using (var archive = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            var entry = archive.CreateEntry(entryName);
            using var writer = new StreamWriter(entry.Open());
            writer.Write(content);
        }

        return ms.ToArray();
    }

    /// <summary>
    /// Creates a ZIP archive in memory containing a single directory entry.
    /// </summary>
    private static byte[] CreateZipWithDirectoryEntry(string directoryName)
    {
        using var ms = new MemoryStream();
        using (var archive = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            // Directory entries in ZIPs have an empty name portion and end with /
            archive.CreateEntry(directoryName);
        }

        return ms.ToArray();
    }

    /// <summary>
    /// Mirrors the zip-slip guard from the Hosted-AgentSkills sample Program.cs.
    /// </summary>
    private static void SafeExtractZip(ZipArchive archive, string destinationDir)
    {
        string destRoot = Path.GetFullPath(destinationDir);
        string destRootWithSep = Path.EndsInDirectorySeparator(destRoot)
            ? destRoot
            : destRoot + Path.DirectorySeparatorChar;

        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;

        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            // Resolve the entry against the destination, then require the result to stay within the
            // destination subtree. A single StartsWith containment check is the only gate to
            // extraction, so any entry that escapes (for example via '..') is rejected.
            string entryPath = Path.GetFullPath(Path.Combine(destRoot, entry.FullName));
            if (!entryPath.StartsWith(destRootWithSep, comparison))
            {
                throw new InvalidOperationException(
                    $"Refusing to extract unsafe path '{entry.FullName}' outside of '{destRoot}'.");
            }

            if (string.IsNullOrEmpty(entry.Name))
            {
                Directory.CreateDirectory(entryPath);
            }
            else
            {
                Directory.CreateDirectory(Path.GetDirectoryName(entryPath)!);
                entry.ExtractToFile(entryPath, overwrite: true);
            }
        }
    }

    /// <summary>
    /// Mirrors the skill name validation from the Hosted-AgentSkills sample Program.cs.
    /// </summary>
    private static bool IsInvalidSkillName(string name) =>
        name.Contains('.') || name.Contains('/') || name.Contains('\\') || Path.IsPathRooted(name);
}
