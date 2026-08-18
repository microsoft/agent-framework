// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

/// <summary>
/// Unit tests for the line-numbering contract on <see cref="AgentFileStore"/>: the published split,
/// the numbering primitive, the narrowing hook, the base <see cref="AgentFileStore.SearchAsync"/>
/// built on top of them, and the guards that keep a store's line numbers honest.
/// </summary>
public class AgentFileStoreContractTests
{
    private const string Needle = "keep me";

    /// <summary>
    /// A store implementing only the mandatory members. Before the contract this could not exist:
    /// <c>SearchAsync</c> was abstract. It now inherits the base implementation and must produce line
    /// numbers that address the same lines the editor edits.
    /// </summary>
    private class ContentOnlyStore : AgentFileStore
    {
        public Dictionary<string, string> Files { get; } = [];

        public override Task WriteAsync(string path, string content, CancellationToken cancellationToken = default)
        {
            this.Files[path] = content;
            return Task.CompletedTask;
        }

        public override Task<string?> ReadAsync(string path, CancellationToken cancellationToken = default)
            => Task.FromResult(this.Files.TryGetValue(path, out string? value) ? value : null);

        public override Task<bool> DeleteAsync(string path, CancellationToken cancellationToken = default)
            => Task.FromResult(this.Files.Remove(path));

        public override Task<IReadOnlyList<FileStoreEntry>> ListChildrenAsync(string directory, CancellationToken cancellationToken = default)
        {
            string prefix = string.IsNullOrEmpty(directory) ? string.Empty : directory + "/";
            var seen = new Dictionary<string, string>();
            foreach (string path in this.Files.Keys)
            {
                if (!path.StartsWith(prefix, StringComparison.Ordinal))
                {
                    continue;
                }

                string tail = path.Substring(prefix.Length);
                int slash = tail.IndexOf('/');
                seen[slash < 0 ? tail : tail.Substring(0, slash)] = slash < 0 ? FileStoreEntry.File : FileStoreEntry.Directory;
            }

            return Task.FromResult<IReadOnlyList<FileStoreEntry>>(
                seen.Select(kvp => new FileStoreEntry(kvp.Key, kvp.Value)).ToList());
        }

        public override Task<bool> FileExistsAsync(string path, CancellationToken cancellationToken = default)
            => Task.FromResult(this.Files.ContainsKey(path));

        public override Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default)
            => Task.CompletedTask;
    }

    /// <summary>A store whose narrowing hook consults an index instead of listing everything.</summary>
    private sealed class NarrowingStore : ContentOnlyStore
    {
        public HashSet<string> Indexed { get; } = [];

        protected override Task<IReadOnlyList<string>> FindMatchingFilesAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<string>>(this.Indexed.OrderBy(x => x, StringComparer.Ordinal).ToList());
    }

    /// <summary>Numbers lines with its own rule, disagreeing with the editor.</summary>
    private class SkewedStore : ContentOnlyStore
    {
        public override Task<IReadOnlyList<FileSearchResult>> SearchAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
            => Task.FromResult<IReadOnlyList<FileSearchResult>>(
            [
                new FileSearchResult
                {
                    FileName = "cfg.txt",
                    Snippet = string.Empty,

                    // Deliberately wrong: the match is on line 2.
                    MatchingLines = [new FileSearchMatch { LineNumber = 1, Line = Needle }],
                }
            ]);
    }

    /// <summary>The skewed store, declaring alignment it does not have. Pins the documented hazard.</summary>
    private sealed class LyingStore : SkewedStore
    {
        public override bool ReportsAlignedLineNumbers => true;
    }

    [Fact]
    public void SplitLines_PublishesTheEditorsRule()
    {
        foreach (string content in new[] { "a\nb\n", "a\rb", "", "x", "a\r\nb\r\n" })
        {
            // Assert
            Assert.Equal(FileEditor.SplitLinesKeepEnds(content), AgentFileStore.SplitLines(content));
        }
    }

    [Fact]
    public void ScanContent_NumbersBySplitLines()
    {
        // Act
        FileSearchResult? result = AgentFileStore.ScanContent("f.txt", "alpha\r\nbeta match\r\ngamma\r\n", new Regex("match", RegexOptions.IgnoreCase));

        // Assert
        Assert.NotNull(result);
        FileSearchMatch match = result!.MatchingLines[0];
        Assert.Equal(AgentFileStore.SplitLines("alpha\r\nbeta match\r\ngamma\r\n")[match.LineNumber - 1], match.Line);
        Assert.Equal("beta match\r\n", match.Line);
    }

    [Fact]
    public async Task StoreWithoutSearch_UsesBasePathAndStaysAlignedAsync()
    {
        // Arrange
        var store = new ContentOnlyStore();
        const string Raw = "alpha\r\nDEBUG = 1\r\nkeep me\r\nDEBUG = 2\r\n";
        await store.WriteAsync("cfg.txt", Raw);

        // Act
        IReadOnlyList<FileSearchResult> results = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Assert: the number grep reports addresses the line the editor will touch.
        FileSearchMatch match = Assert.Single(Assert.Single(results).MatchingLines);
        Assert.Equal(3, match.LineNumber);
        Assert.Equal("keep me\r\n", match.Line);
        Assert.Equal(match.Line, FileEditor.SliceLines(Raw, match.LineNumber, match.LineNumber)[0]);
    }

    [Fact]
    public async Task BaseSearch_ReappliesGlobAndRecursionWhenAStoreOverReturnsAsync()
    {
        // Arrange: the hook returns everything, ignoring both the glob and the recursion flag.
        var store = new NarrowingStore();
        await store.WriteAsync("top.md", Needle);
        await store.WriteAsync("notes.txt", Needle);
        await store.WriteAsync("nested/deep.md", Needle);
        foreach (string name in store.Files.Keys)
        {
            store.Indexed.Add(name);
        }

        // Act
        IReadOnlyList<FileSearchResult> topLevelMarkdown = await store.SearchAsync(string.Empty, Needle, "*.md", recursive: true);
        IReadOnlyList<FileSearchResult> allMarkdown = await store.SearchAsync(string.Empty, Needle, "**/*.md", recursive: true);
        IReadOnlyList<FileSearchResult> shallow = await store.SearchAsync(string.Empty, Needle, recursive: false);

        // Assert: the glob is re-applied, using this SDK's Matcher semantics where "*" does not
        // cross "/" (unlike the Python side's fnmatch, where it does).
        Assert.Equal(["top.md"], topLevelMarkdown.Select(r => r.FileName));
        Assert.Equal(["nested/deep.md", "top.md"], allMarkdown.Select(r => r.FileName).OrderBy(x => x, StringComparer.Ordinal));

        // And the non-recursive rule still excludes the nested file.
        Assert.Equal(["notes.txt", "top.md"], shallow.Select(r => r.FileName).OrderBy(x => x, StringComparer.Ordinal));
    }

    [Fact]
    public async Task BaseSearch_NarrowsThroughTheHookAsync()
    {
        // Arrange: three files match, but only one is indexed.
        var store = new NarrowingStore();
        for (int i = 0; i < 3; i++)
        {
            await store.WriteAsync($"f{i}.txt", $"alpha\n{Needle}\n");
        }

        store.Indexed.Add("f1.txt");

        // Act
        IReadOnlyList<FileSearchResult> results = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Assert: narrowing decides what is read; the base still numbers it.
        Assert.Equal("f1.txt", Assert.Single(results).FileName);
        Assert.Equal(2, results[0].MatchingLines[0].LineNumber);
    }

    [Fact]
    public async Task ShippedStores_DeclareTheirLineNumbersAlignedAsync()
    {
        // Assert: both report through ScanContent, so neither is ever re-checked. Asserting only one
        // of them would let the other's override be dropped with every test still green, silently
        // doubling reads on every grep.
        Assert.True(new InMemoryAgentFileStore().ReportsAlignedLineNumbers);
        Assert.True(new FileSystemAgentFileStore(Path.GetTempPath()).ReportsAlignedLineNumbers);
        Assert.False(new ContentOnlyStore().ReportsAlignedLineNumbers);

        // And a store on the base path is recognised without declaring anything, because the base
        // implementation tags the results it numbered.
        var store = new ContentOnlyStore();
        await store.WriteAsync("f.txt", Needle);
        IReadOnlyList<FileSearchResult> results = await store.SearchAsync(string.Empty, Needle, recursive: true);
        await SearchAlignment.ThrowIfMisalignedAsync(store, string.Empty, results, Needle, CancellationToken.None);
    }

    [Fact]
    public async Task Alignment_RefusesAStoreWhoseLineNumbersAreSkewedAsync()
    {
        // Arrange: the match is on line 2, but the store reports line 1.
        var store = new SkewedStore();
        await store.WriteAsync("cfg.txt", $"alpha\n{Needle}\n");
        IReadOnlyList<FileSearchResult> results = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Act + Assert
        InvalidOperationException error = await Assert.ThrowsAsync<InvalidOperationException>(
            () => SearchAlignment.ThrowIfMisalignedAsync(store, string.Empty, results, Needle, CancellationToken.None));
        Assert.Contains("do not line up", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Alignment_BelievesAStoreThatDeclaresItsNumbersAlignedAsync()
    {
        // Arrange: the same wrong numbers, but the store declares alignment.
        var store = new LyingStore();
        await store.WriteAsync("cfg.txt", $"alpha\n{Needle}\n");
        IReadOnlyList<FileSearchResult> results = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Act: no throw. The opt-out is a promise, not a hint.
        await SearchAlignment.ThrowIfMisalignedAsync(store, string.Empty, results, Needle, CancellationToken.None);

        // Assert
        Assert.Equal(1, results[0].MatchingLines[0].LineNumber);
    }

    [Fact]
    public void ApplyReplaceLines_ExpectedLineMatching_AppliesTheEdit()
    {
        // Act
        string result = FileEditor.ApplyReplaceLines(
            "one\ntwo\nthree\n",
            [new FileLineEdit { LineNumber = 2, NewLine = "TWO\n", ExpectedLine = "two" }]);

        // Assert
        Assert.Equal("one\nTWO\nthree\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_ExpectedLineDiffering_Throws()
    {
        // Act + Assert: a stale or mis-numbered edit is refused rather than applied.
        ArgumentException error = Assert.Throws<ArgumentException>(() =>
            FileEditor.ApplyReplaceLines(
                "one\ntwo\nthree\n",
                [new FileLineEdit { LineNumber = 3, NewLine = "X\n", ExpectedLine = "two" }]));

        Assert.Contains("does not contain the expected text", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ApplyReplaceLines_ExpectedLineIgnoresTheTerminator()
    {
        // Act: a line fed straight back from grep still carries its terminator.
        string result = FileEditor.ApplyReplaceLines(
            "alpha\r\nbeta\r\n",
            [new FileLineEdit { LineNumber = 2, NewLine = "BETA\r\n", ExpectedLine = "beta\r\n" }]);

        // Assert
        Assert.Equal("alpha\r\nBETA\r\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_WithoutExpectedLine_IsUnchanged()
    {
        // Act: the guard is opt-in.
        string result = FileEditor.ApplyReplaceLines("one\ntwo\n", [new FileLineEdit { LineNumber = 1, NewLine = "ONE\n" }]);

        // Assert
        Assert.Equal("ONE\ntwo\n", result);
    }

    /// <summary>Overrides SearchAsync but delegates to the base implementation some of the time.</summary>
    private sealed class SometimesDelegatesStore : ContentOnlyStore
    {
        public bool Delegate { get; set; }

        public override Task<IReadOnlyList<FileSearchResult>> SearchAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
            => this.Delegate
                ? base.SearchAsync(directory, regexPattern, globPattern, recursive, cancellationToken)
                : Task.FromResult<IReadOnlyList<FileSearchResult>>(
                [
                    new FileSearchResult
                    {
                        FileName = "cfg.txt",
                        Snippet = string.Empty,

                        // Wrong: the match is on line 2.
                        MatchingLines = [new FileSearchMatch { LineNumber = 1, Line = Needle }],
                    }
                ]);
    }

    [Fact]
    public async Task Alignment_IsNotDisabledByAnEarlierDelegationToBaseSearchAsync()
    {
        // Arrange: a store that falls back to the base implementation sometimes -- an index
        // warm-up, an unindexed directory. That must not buy permanent trust for the results
        // it numbers itself.
        var store = new SometimesDelegatesStore();
        await store.WriteAsync("cfg.txt", $"alpha\n{Needle}\n");

        store.Delegate = true;
        _ = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Act: now it serves its own, skewed numbering.
        store.Delegate = false;
        IReadOnlyList<FileSearchResult> skewed = await store.SearchAsync(string.Empty, Needle, recursive: true);

        // Assert: still checked, still refused.
        await Assert.ThrowsAsync<InvalidOperationException>(
            () => SearchAlignment.ThrowIfMisalignedAsync(store, string.Empty, skewed, Needle, CancellationToken.None));
    }
}
