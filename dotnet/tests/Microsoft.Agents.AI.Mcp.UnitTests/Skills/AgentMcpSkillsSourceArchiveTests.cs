// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Formats.Tar;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Unit tests for archive-distributed skill handling in <see cref="AgentMcpSkillsSource"/>.
/// </summary>
public sealed class AgentMcpSkillsSourceArchiveTests : IDisposable
{
    private const string ArchivedSkillMd = """
        ---
        name: archived-skill
        description: A skill delivered as an archive.
        ---
        # Archived Skill

        Body from the archive.
        """;

    private const string StaleSkillMd = """
        ---
        name: stale-skill
        description: Left over from a previous session.
        ---
        Old content.
        """;

    private const string SkillAMd = """
        ---
        name: skill-a
        description: Skill A.
        ---
        Content A.
        """;

    private const string SkillBMd = """
        ---
        name: skill-b
        description: Skill B.
        ---
        Content B.
        """;

    private readonly string _extractionRoot =
        Path.Combine(Path.GetTempPath(), "af-mcp-archive-tests", Guid.NewGuid().ToString("N"));

    private const int ManyFileArchiveFileCount = 60;

    [Fact]
    public async Task GetSkillsAsync_ZipArchive_DiscoversSkillAsync()
    {
        // Arrange
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ZipArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        var skill = Assert.Single(skills);
        Assert.Equal("archived-skill", skill.Frontmatter.Name);
        Assert.Equal("A skill delivered as an archive.", skill.Frontmatter.Description);
        Assert.Contains("Body from the archive.", await skill.GetContentAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_TarGzArchive_DiscoversSkillAsync()
    {
        // Arrange
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<TarGzArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        var skill = Assert.Single(skills);
        Assert.Equal("archived-skill", skill.Frontmatter.Name);
        Assert.Contains("Body from the archive.", await skill.GetContentAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveWithScript_SurfacesScriptAsReadableResourceAsync()
    {
        // Arrange - archive bundles a script file alongside SKILL.md. Over MCP, scripts must never be
        // executable; they are surfaced as readable resources only when explicitly included via options.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ZipWithScriptServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions
        {
            ArchiveSkillsDirectory = this._extractionRoot,
            ArchiveResourceExtensions = [".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt", ".py"],
        };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var resource = await skill.GetResourceAsync("scripts/run.py");

        // Assert - the .py file is readable as a resource (not an executable script).
        Assert.NotNull(resource);
        var content = await resource!.ReadAsync();
        Assert.Equal("print('hello')", content);
    }

    [Fact]
    public async Task GetSkillsAsync_TwoSourcesWithSeparateDirectories_DoNotCollideAsync()
    {
        // Arrange - two servers publish an archive skill with the SAME name but different content.
        // Pointing each source at its own directory keeps their extracted content separate.
        await using var serverA = new InMemoryMcpServer(builder => builder.WithResources<SharedNameServerA>());
        await using var clientA = await serverA.CreateClientAsync();
        await using var serverB = new InMemoryMcpServer(builder => builder.WithResources<SharedNameServerB>());
        await using var clientB = await serverB.CreateClientAsync();

        var sourceA = new AgentMcpSkillsSource(clientA, new() { ArchiveSkillsDirectory = Path.Combine(this._extractionRoot, "a") });
        var sourceB = new AgentMcpSkillsSource(clientB, new() { ArchiveSkillsDirectory = Path.Combine(this._extractionRoot, "b") });

        // Act
        var skillA = Assert.Single(await sourceA.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        var skillB = Assert.Single(await sourceB.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert - each source kept its own content despite the shared skill name.
        Assert.Equal("shared-skill", skillA.Frontmatter.Name);
        Assert.Equal("shared-skill", skillB.Frontmatter.Name);
        Assert.Contains("Content from server A.", await skillA.GetContentAsync());
        Assert.Contains("Content from server B.", await skillB.GetContentAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_FirstRun_PrunesLeftoverSkillDirectoryAsync()
    {
        // Arrange - a leftover skill directory from a previous session sits in the provided directory.
        string staleDir = Path.Combine(this._extractionRoot, "stale-skill");
        Directory.CreateDirectory(staleDir);
        await File.WriteAllTextAsync(Path.Combine(staleDir, "SKILL.md"), StaleSkillMd);

        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ZipArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - the leftover directory is pruned and only the advertised skill remains.
        Assert.False(Directory.Exists(staleDir));
        var skill = Assert.Single(skills);
        Assert.Equal("archived-skill", skill.Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SkillNoLongerAdvertised_IsPrunedAsync()
    {
        // Arrange - an earlier run extracts skill-a and skill-b into the shared directory.
        await using var fullServer = new InMemoryMcpServer(builder => builder.WithResources<TwoSkillServer>());
        await using var fullClient = await fullServer.CreateClientAsync();
        var firstSource = new AgentMcpSkillsSource(fullClient, new() { ArchiveSkillsDirectory = this._extractionRoot });
        var firstSkills = await firstSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());
        Assert.Equal(2, firstSkills.Count);
        Assert.True(Directory.Exists(Path.Combine(this._extractionRoot, "skill-b")));

        // Act - a later run sees only skill-a.
        await using var partialServer = new InMemoryMcpServer(builder => builder.WithResources<OneSkillServer>());
        await using var partialClient = await partialServer.CreateClientAsync();
        var secondSource = new AgentMcpSkillsSource(partialClient, new() { ArchiveSkillsDirectory = this._extractionRoot });
        var secondSkills = await secondSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - skill-b's directory was pruned; only skill-a remains.
        var skill = Assert.Single(secondSkills);
        Assert.Equal("skill-a", skill.Frontmatter.Name);
        Assert.False(Directory.Exists(Path.Combine(this._extractionRoot, "skill-b")));
        Assert.True(Directory.Exists(Path.Combine(this._extractionRoot, "skill-a")));
    }

    [Fact]
    public async Task GetSkillsAsync_ServerListsNoArchives_PrunesLeftoversAsync()
    {
        // Arrange - a leftover skill directory exists but the server advertises no archive skills.
        string staleDir = Path.Combine(this._extractionRoot, "stale-skill");
        Directory.CreateDirectory(staleDir);
        await File.WriteAllTextAsync(Path.Combine(staleDir, "SKILL.md"), StaleSkillMd);

        await using var server = new InMemoryMcpServer(builder => builder.WithResources<NoArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - the leftover directory is pruned and no skills are returned.
        Assert.Empty(skills);
        Assert.False(Directory.Exists(staleDir));
    }

    [Fact]
    public async Task GetSkillsAsync_SecondDiscovery_ReExtractsContentAsync()
    {
        // Arrange - a first run extracts server A's content into the shared directory.
        await using (var serverA = new InMemoryMcpServer(builder => builder.WithResources<SharedNameServerA>()))
        await using (var clientA = await serverA.CreateClientAsync())
        {
            var firstSource = new AgentMcpSkillsSource(clientA, new() { ArchiveSkillsDirectory = this._extractionRoot });
            Assert.Single(await firstSource.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));
        }

        // Act - a second run over the same directory re-extracts server B's content.
        await using var serverB = new InMemoryMcpServer(builder => builder.WithResources<SharedNameServerB>());
        await using var clientB = await serverB.CreateClientAsync();
        var source = new AgentMcpSkillsSource(clientB, new() { ArchiveSkillsDirectory = this._extractionRoot });
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert - the content was replaced with server B's.
        Assert.Contains("Content from server B.", await skill.GetContentAsync());
    }

    [Fact]
    public async Task GetSkillsAsync_PreExtractionCleanupFails_DoesNotDiscoverStaleSkillAsync()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        // Arrange - a stale skill directory contains a locked file, causing recursive deletion to fail.
        string skillDirectory = Path.Combine(this._extractionRoot, "shared-skill");
        Directory.CreateDirectory(skillDirectory);
        await File.WriteAllTextAsync(Path.Combine(skillDirectory, "SKILL.md"), """
            ---
            name: shared-skill
            description: Shared.
            ---
            Stale content.
            """);

        string lockedResourcePath = Path.Combine(skillDirectory, "locked.txt");
        await using var lockedResource = new FileStream(lockedResourcePath, FileMode.Create, FileAccess.ReadWrite, FileShare.None);

        await using var server = new InMemoryMcpServer(builder => builder.WithResources<SharedNameServerB>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client, new() { ArchiveSkillsDirectory = this._extractionRoot });

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - failed cleanup prevents the stale directory from being proxied to AgentFileSkillsSource.
        Assert.Empty(skills);
        Assert.True(File.Exists(lockedResourcePath));
    }

    [Fact]
    public void Extract_ZipSlipEntry_DoesNotEscapeTargetDirectory()
    {
        // Arrange - a malicious zip whose entry traverses out of the target directory.
        byte[] zip = BuildZip(("../escaped.txt", "pwned"), ("SKILL.md", ArchivedSkillMd));
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act
        AgentMcpSkillArchiveExtractor.Extract(zip, ArchiveFormat.Zip, target);

        // Assert - the traversal entry was skipped; only the safe entry was written.
        Assert.False(File.Exists(Path.Combine(this._extractionRoot, "escaped.txt")));
        Assert.True(File.Exists(Path.Combine(target, "SKILL.md")));
    }

    [Fact]
    public void Extract_CaseVariantZipSlipEntry_DoesNotEscapeTargetDirectory()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        // Arrange - on case-sensitive file systems, "skill" is a sibling of "Skill", not the target.
        byte[] zip = BuildZip(("../skill/escaped.txt", "pwned"), ("SKILL.md", ArchivedSkillMd));
        string target = Path.Combine(this._extractionRoot, "Skill");

        // Act
        AgentMcpSkillArchiveExtractor.Extract(zip, ArchiveFormat.Zip, target);

        // Assert - the case-variant traversal entry was skipped; only the safe entry was written.
        Assert.False(File.Exists(Path.Combine(this._extractionRoot, "skill", "escaped.txt")));
        Assert.True(File.Exists(Path.Combine(target, "SKILL.md")));
    }

    [Fact]
    public void Extract_ArchiveExceedsDefaultFileCount_Throws()
    {
        // Arrange - more files than the default cap.
        var entries = Enumerable.Range(0, AgentMcpSkillArchiveExtractor.DefaultMaxFileCount + 1)
            .Select(i => ($"file{i}.txt", "x"))
            .ToArray();
        byte[] zip = BuildZip(entries);
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act / Assert
        Assert.Throws<InvalidDataException>(
            () => AgentMcpSkillArchiveExtractor.Extract(zip, ArchiveFormat.Zip, target));
    }

    [Fact]
    public void Extract_ArchiveExceedsDefaultUncompressedSize_Throws()
    {
        // Arrange - a single file larger than the default uncompressed budget (1 MB).
        string oversized = new('x', (int)AgentMcpSkillArchiveExtractor.DefaultMaxUncompressedSizeBytes + 1);
        byte[] zip = BuildZip(("SKILL.md", oversized));
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act / Assert
        Assert.Throws<InvalidDataException>(
            () => AgentMcpSkillArchiveExtractor.Extract(zip, ArchiveFormat.Zip, target));
    }

    [Fact]
    public void Extract_TarGzExceedsUncompressedSize_Throws()
    {
        // Arrange - a gzip-compressed tar whose expansion exceeds the default budget. The ZIP pre-gate
        // does not apply here, so this exercises the authoritative streaming cap (CopyWithLimit).
        string oversized = new('x', (int)AgentMcpSkillArchiveExtractor.DefaultMaxUncompressedSizeBytes + 1);
        byte[] tarGz = BuildTarGz(("SKILL.md", oversized));
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act / Assert
        Assert.Throws<InvalidDataException>(
            () => AgentMcpSkillArchiveExtractor.Extract(tarGz, ArchiveFormat.TarGz, target));
    }

    [Fact]
    public void Extract_TarWithLinkEntries_SkipsLinksAndExtractsRegularFiles()
    {
        // Arrange - a tar.gz containing symbolic-link and hard-link entries whose targets escape the
        // target directory, alongside a regular file. Link entries must be skipped so an archive cannot
        // create links that point outside the target directory.
        byte[] tarGz = BuildTarGzFromEntries(
            new PaxTarEntry(TarEntryType.SymbolicLink, "evil-symlink") { LinkName = "../../escaped.txt" },
            new PaxTarEntry(TarEntryType.HardLink, "evil-hardlink") { LinkName = "../../escaped.txt" },
            new PaxTarEntry(TarEntryType.RegularFile, "SKILL.md")
            {
                DataStream = new MemoryStream(Encoding.UTF8.GetBytes(ArchivedSkillMd)),
            });
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act
        AgentMcpSkillArchiveExtractor.Extract(tarGz, ArchiveFormat.TarGz, target);

        // Assert - only the regular file is materialized; neither link entry is written.
        Assert.True(File.Exists(Path.Combine(target, "SKILL.md")));
        Assert.False(File.Exists(Path.Combine(target, "evil-symlink")));
        Assert.False(File.Exists(Path.Combine(target, "evil-hardlink")));
        Assert.Single(Directory.GetFileSystemEntries(target));
    }

    [Fact]
    public void Extract_WithinDefaultLimits_Succeeds()
    {
        // Arrange - a typical small archive that is comfortably within the default limits.
        byte[] zip = BuildZip(("SKILL.md", ArchivedSkillMd), ("reference.md", "Some reference content."));
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act
        AgentMcpSkillArchiveExtractor.Extract(zip, ArchiveFormat.Zip, target);

        // Assert
        Assert.True(File.Exists(Path.Combine(target, "SKILL.md")));
        Assert.True(File.Exists(Path.Combine(target, "reference.md")));
    }

    [Fact]
    public void Extract_RaisedLimits_AllowsLargerArchive()
    {
        // Arrange - an archive that exceeds the default file count but fits within raised limits.
        var entries = Enumerable.Range(0, AgentMcpSkillArchiveExtractor.DefaultMaxFileCount + 1)
            .Select(i => ($"file{i}.txt", "x"))
            .ToArray();
        byte[] zip = BuildZip(entries);
        string target = Path.Combine(this._extractionRoot, "skill");

        // Act
        AgentMcpSkillArchiveExtractor.Extract(
            zip,
            ArchiveFormat.Zip,
            target,
            maxFileCount: entries.Length + 1);

        // Assert - every entry was extracted.
        Assert.Equal(entries.Length, Directory.GetFiles(target).Length);
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveExceedsDefaultFileCount_SkillSkippedAsync()
    {
        // Arrange - the archive has more files than the default cap, so extraction fails and the skill is skipped.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ManyFileArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var source = new AgentMcpSkillsSource(client, new() { ArchiveSkillsDirectory = this._extractionRoot });

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveExceedsConfiguredArchiveSize_SkillSkippedAsync()
    {
        // Arrange - the valid archive is larger than the configured downloaded-archive byte cap.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ZipArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions
        {
            ArchiveSkillsDirectory = this._extractionRoot,
            ArchiveMaxSizeBytes = 1,
        };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_RaisedFileCountOption_LoadsLargerArchiveAsync()
    {
        // Arrange - raising ArchiveMaxFileCount lets the larger archive through.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<ManyFileArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions
        {
            ArchiveSkillsDirectory = this._extractionRoot,
            ArchiveMaxFileCount = ManyFileArchiveFileCount + 1,
        };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skill = Assert.Single(await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create()));

        // Assert
        Assert.Equal("archived-skill", skill.Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_EntryMissingName_SkillSkippedAsync()
    {
        // Arrange - an archive index entry with a null/empty name is not actionable.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<MissingNameServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert - the invalid entry is skipped; no skills are surfaced.
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_EntryWithInvalidNameChars_SkillSkippedAsync()
    {
        // Arrange - a name containing path separator characters is not a valid directory name.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<InvalidNameCharsServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_EntryMissingUrl_SkillSkippedAsync()
    {
        // Arrange - an archive entry without a url cannot be downloaded.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<MissingUrlServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveWithUnsupportedFormat_SkillSkippedAsync()
    {
        // Arrange - the archive payload does not match any known format (no magic bytes, no matching
        // media type, no recognized URL extension).
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<UnsupportedFormatServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveReturnsTextNotBlob_SkillSkippedAsync()
    {
        // Arrange - the archive resource returns text content instead of a binary blob.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<TextOnlyArchiveServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);

        // Act
        var skills = await source.GetSkillsAsync(TestAgentSkillsSourceContextFactory.Create());

        // Assert
        Assert.Empty(skills);
    }

    [Fact]
    public async Task GetSkillsAsync_ConcurrentCalls_ReconcilesArchiveDirectorySafelyAsync()
    {
        // Arrange - a fixed extraction directory means every concurrent call reconciles the same
        // on-disk location. The per-instance lock must serialize that reconcile/extract/read work so
        // that no call observes a half-extracted or mid-prune directory.
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<TwoSkillServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act - hammer the source from many threads at once.
        var tasks = Enumerable.Range(0, 20)
            .Select(_ => Task.Run(() => source.GetSkillsAsync(context)))
            .ToArray();
        var results = await Task.WhenAll(tasks);

        // Assert - every call returns both skills with intact content.
        foreach (var skills in results)
        {
            Assert.Equal(2, skills.Count);

            var byName = skills.ToDictionary(s => s.Frontmatter.Name);
            Assert.Contains("Content A.", await byName["skill-a"].GetContentAsync());
            Assert.Contains("Content B.", await byName["skill-b"].GetContentAsync());
        }
    }

    [Fact]
    public async Task GetSkillsAsync_ArchiveUpdatedBetweenCalls_ReturnsUpdatedContentAsync()
    {
        // Arrange - a mutable server whose archive body the test can change to simulate the skill
        // being republished. Because the loader re-extracts under its reconcile lock on every call,
        // a query issued after the update (and any calls queued behind the lock) must observe the
        // new content, never a stale pre-update snapshot.
        MutableSkillServer.Body = "Version one.";
        await using var server = new InMemoryMcpServer(builder => builder.WithResources<MutableSkillServer>());
        await using var client = await server.CreateClientAsync();
        var options = new AgentMcpSkillsSourceOptions { ArchiveSkillsDirectory = this._extractionRoot };
        var source = new AgentMcpSkillsSource(client, options);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act - the initial load observes the original content.
        var before = await source.GetSkillsAsync(context);

        // The skill is republished with new content.
        MutableSkillServer.Body = "Version two.";

        // Fire many post-update calls at once; they serialize behind the reconcile lock.
        var tasks = Enumerable.Range(0, 10)
            .Select(_ => Task.Run(() => source.GetSkillsAsync(context)))
            .ToArray();
        var afterResults = await Task.WhenAll(tasks);

        // Assert - the first load saw the old content.
        Assert.Contains("Version one.", await Assert.Single(before).GetContentAsync());

        // Every post-update call sees the new content and not the stale pre-update body.
        foreach (var skills in afterResults)
        {
            var content = await Assert.Single(skills).GetContentAsync();
            Assert.Contains("Version two.", content);
            Assert.DoesNotContain("Version one.", content);
        }
    }

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(this._extractionRoot))
            {
                Directory.Delete(this._extractionRoot, recursive: true);
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            // Best-effort cleanup.
        }
    }

    private static byte[] BuildZip(params (string Path, string Content)[] entries)
    {
        using var ms = new MemoryStream();
        using (var archive = new ZipArchive(ms, ZipArchiveMode.Create, leaveOpen: true))
        {
            foreach (var (path, content) in entries)
            {
                ZipArchiveEntry entry = archive.CreateEntry(path);
                using Stream stream = entry.Open();
                byte[] bytes = Encoding.UTF8.GetBytes(content);
                stream.Write(bytes, 0, bytes.Length);
            }
        }

        return ms.ToArray();
    }

    private static byte[] BuildTarGz(params (string Path, string Content)[] entries)
    {
        using var ms = new MemoryStream();
        using (var gzip = new GZipStream(ms, CompressionMode.Compress, leaveOpen: true))
        using (var writer = new TarWriter(gzip, leaveOpen: true))
        {
            foreach (var (path, content) in entries)
            {
                var entry = new PaxTarEntry(TarEntryType.RegularFile, path)
                {
                    DataStream = new MemoryStream(Encoding.UTF8.GetBytes(content)),
                };
                writer.WriteEntry(entry);
            }
        }

        return ms.ToArray();
    }

    private static byte[] BuildTarGzFromEntries(params TarEntry[] entries)
    {
        using var ms = new MemoryStream();
        using (var gzip = new GZipStream(ms, CompressionMode.Compress, leaveOpen: true))
        using (var writer = new TarWriter(gzip, leaveOpen: true))
        {
            foreach (var entry in entries)
            {
                writer.WriteEntry(entry);
            }
        }

        return ms.ToArray();
    }

    private static string ArchiveIndex(string skillName, string url) => $$"""
        {
          "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
          "skills": [
            {
              "name": "{{skillName}}",
              "type": "archive",
              "description": "A skill delivered as an archive.",
              "url": "{{url}}"
            }
          ]
        }
        """;

    #region Resource classes (registered with the MCP server via WithResources<T>)

#pragma warning disable CA1812

    [McpServerResourceType]
    private sealed class ZipArchiveServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("archived-skill", "skill://archives/archived-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/archived-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", ArchivedSkillMd)),
            "skill://archives/archived-skill.zip",
            "application/zip");
    }

    [McpServerResourceType]
    private sealed class TarGzArchiveServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("archived-skill", "skill://archives/archived-skill.tar.gz");

        [McpServerResource(UriTemplate = "skill://archives/archived-skill.tar.gz", Name = "archive", MimeType = "application/gzip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildTarGz(("SKILL.md", ArchivedSkillMd)),
            "skill://archives/archived-skill.tar.gz",
            "application/gzip");
    }

    [McpServerResourceType]
    private sealed class ZipWithScriptServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("archived-skill", "skill://archives/archived-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/archived-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", ArchivedSkillMd), ("scripts/run.py", "print('hello')")),
            "skill://archives/archived-skill.zip",
            "application/zip");
    }

    [McpServerResourceType]
    private sealed class ManyFileArchiveServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("archived-skill", "skill://archives/archived-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/archived-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive()
        {
            var entries = new List<(string Path, string Content)> { ("SKILL.md", ArchivedSkillMd) };
            for (int i = 0; i < ManyFileArchiveFileCount - 1; i++)
            {
                entries.Add(($"reference/file{i}.txt", "x"));
            }

            return BlobResourceContents.FromBytes(
                BuildZip(entries.ToArray()),
                "skill://archives/archived-skill.zip",
                "application/zip");
        }
    }

    [McpServerResourceType]
    private sealed class SharedNameServerA
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("shared-skill", "skill://archives/shared-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/shared-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", """
                ---
                name: shared-skill
                description: Shared.
                ---
                Content from server A.
                """)),
            "skill://archives/shared-skill.zip",
            "application/zip");
    }

    [McpServerResourceType]
    private sealed class SharedNameServerB
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("shared-skill", "skill://archives/shared-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/shared-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", """
                ---
                name: shared-skill
                description: Shared.
                ---
                Content from server B.
                """)),
            "skill://archives/shared-skill.zip",
            "application/zip");
    }

    [McpServerResourceType]
    private sealed class TwoSkillServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                { "name": "skill-a", "type": "archive", "description": "Skill A.", "url": "skill://archives/skill-a.zip" },
                { "name": "skill-b", "type": "archive", "description": "Skill B.", "url": "skill://archives/skill-b.zip" }
              ]
            }
            """;

        [McpServerResource(UriTemplate = "skill://archives/skill-a.zip", Name = "skill-a", MimeType = "application/zip")]
        public static BlobResourceContents SkillA() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", SkillAMd)), "skill://archives/skill-a.zip", "application/zip");

        [McpServerResource(UriTemplate = "skill://archives/skill-b.zip", Name = "skill-b", MimeType = "application/zip")]
        public static BlobResourceContents SkillB() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", SkillBMd)), "skill://archives/skill-b.zip", "application/zip");
    }

    [McpServerResourceType]
    private sealed class MutableSkillServer
    {
        // Toggled by the test to simulate the server republishing the skill with new content.
        public static volatile string Body = "Version one.";

        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("archived-skill", "skill://archives/archived-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/archived-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", $$"""
                ---
                name: archived-skill
                description: A skill delivered as an archive.
                ---
                {{Body}}
                """)),
            "skill://archives/archived-skill.zip",
            "application/zip");
    }

    [McpServerResourceType]
    private sealed class OneSkillServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("skill-a", "skill://archives/skill-a.zip");

        [McpServerResource(UriTemplate = "skill://archives/skill-a.zip", Name = "skill-a", MimeType = "application/zip")]
        public static BlobResourceContents SkillA() => BlobResourceContents.FromBytes(
            BuildZip(("SKILL.md", SkillAMd)), "skill://archives/skill-a.zip", "application/zip");
    }

    [McpServerResourceType]
    private sealed class NoArchiveServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": []
            }
            """;
    }

    [McpServerResourceType]
    private sealed class MissingNameServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                { "name": "", "type": "archive", "description": "No name.", "url": "skill://archives/x.zip" }
              ]
            }
            """;
    }

    [McpServerResourceType]
    private sealed class InvalidNameCharsServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                { "name": "../escape", "type": "archive", "description": "Bad name.", "url": "skill://archives/x.zip" }
              ]
            }
            """;
    }

    [McpServerResourceType]
    private sealed class MissingUrlServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => """
            {
              "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
              "skills": [
                { "name": "good-name", "type": "archive", "description": "No url.", "url": "" }
              ]
            }
            """;
    }

    [McpServerResourceType]
    private sealed class UnsupportedFormatServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("bad-format", "skill://archives/bad-format.bin");

        [McpServerResource(UriTemplate = "skill://archives/bad-format.bin", Name = "archive", MimeType = "application/octet-stream")]
        public static BlobResourceContents Archive() => BlobResourceContents.FromBytes(
            Encoding.UTF8.GetBytes("not an archive"),
            "skill://archives/bad-format.bin",
            "application/octet-stream");
    }

    [McpServerResourceType]
    private sealed class TextOnlyArchiveServer
    {
        [McpServerResource(UriTemplate = "skill://index.json", Name = "index", MimeType = "application/json")]
        public static string Index() => ArchiveIndex("text-skill", "skill://archives/text-skill.zip");

        [McpServerResource(UriTemplate = "skill://archives/text-skill.zip", Name = "archive", MimeType = "application/zip")]
        public static string Archive() => "this is not binary";
    }

#pragma warning restore CA1812

    #endregion
}
