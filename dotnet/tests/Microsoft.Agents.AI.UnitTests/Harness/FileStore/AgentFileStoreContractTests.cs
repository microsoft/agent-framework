// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
        // Arrange: three files match, but only one is indexed. Under-returning breaks the hook's
        // contract; it is done here because nothing else proves the hook chose what got read.
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

        Assert.Contains("does not match the expected text", error.Message, StringComparison.Ordinal);
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

    /// <summary>Lists children without observing the token, and counts how often it is asked.</summary>
    private sealed class CountingListStore : ContentOnlyStore
    {
        public int Listings { get; private set; }

        public override Task<IReadOnlyList<FileStoreEntry>> ListChildrenAsync(string directory, CancellationToken cancellationToken = default)
        {
            this.Listings++;
            return base.ListChildrenAsync(directory, CancellationToken.None);
        }
    }

    [Fact]
    public async Task BaseSearch_StopsWalkingWhenCancelledEvenIfTheStoreIgnoresTheTokenAsync()
    {
        // Arrange — twenty directories to walk, and a store that takes the token and never reads it,
        // which is the shape that leaves a cancelled walk enumerating the whole hierarchy.
        var store = new CountingListStore();
        for (int index = 0; index < 20; index++)
        {
            await store.WriteAsync($"dir{index}/f.txt", Needle);
        }

        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => store.SearchAsync(string.Empty, Needle, recursive: true, cancellationToken: cts.Token));

        // Assert — the walk must stop at once. Throwing alone proves nothing here, because
        // SearchAsync checks the token itself once FindMatchingFilesAsync has already returned.
        Assert.Equal(0, store.Listings);
    }

    [Fact]
    public void ScanContent_NullFileName_Throws()
    {
        // Arrange — a pattern that matches, since a non-matching scan returns null and hides the problem.
        var regex = new Regex(Needle, RegexOptions.IgnoreCase);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => AgentFileStore.ScanContent(null!, Needle, regex));
    }
}
