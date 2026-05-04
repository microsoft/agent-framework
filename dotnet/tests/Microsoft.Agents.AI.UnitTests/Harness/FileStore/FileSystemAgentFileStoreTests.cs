// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

public sealed class FileSystemAgentFileStoreTests : IDisposable
{
    private readonly string _rootDir;
    private readonly FileSystemAgentFileStore _store;

    public FileSystemAgentFileStoreTests()
    {
        this._rootDir = Path.Combine(Path.GetTempPath(), "FileSystemAgentFileStoreTests_" + Guid.NewGuid().ToString("N"));
        this._store = new FileSystemAgentFileStore(this._rootDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._rootDir))
        {
            Directory.Delete(this._rootDir, recursive: true);
        }
    }

    #region Constructor

    [Fact]
    public void Constructor_CreatesRootDirectory()
    {
        // Assert
        Assert.True(Directory.Exists(this._rootDir));
    }

    [Fact]
    public void Constructor_NullRootDirectory_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FileSystemAgentFileStore(null!));
    }

    [Fact]
    public void Constructor_EmptyRootDirectory_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new FileSystemAgentFileStore(""));
    }

    [Fact]
    public void Constructor_WhitespaceRootDirectory_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => new FileSystemAgentFileStore("   "));
    }

    #endregion

    #region Path Traversal Rejection

    [Fact]
    public async Task WriteFileAsync_DotDotSegment_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteFileAsync("../escape.txt", "content"));
    }

    [Fact]
    public async Task ReadFileAsync_AbsolutePath_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.ReadFileAsync("/etc/passwd"));
    }

    [Fact]
    public async Task DeleteFileAsync_DriveRootedPath_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.DeleteFileAsync("C:\\temp\\file.txt"));
    }

    [Fact]
    public async Task WriteFileAsync_DotSegment_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteFileAsync("./file.txt", "content"));
    }

    [Fact]
    public async Task WriteFileAsync_DoubleDotsInFileName_AllowedAsync()
    {
        // Arrange — "notes..md" contains ".." but is not a ".." segment
        await this._store.WriteFileAsync("notes..md", "content");

        // Act
        string? result = await this._store.ReadFileAsync("notes..md");

        // Assert
        Assert.Equal("content", result);
    }

    [Fact]
    public async Task WriteFileAsync_TrailingSlash_NormalizesAsync()
    {
        // Act — trailing slash is trimmed during normalization.
        await this._store.WriteFileAsync("subdir/", "content");

        // Assert — the file is accessible via the normalized name.
        string? result = await this._store.ReadFileAsync("subdir");
        Assert.Equal("content", result);
    }

    #endregion

    #region Write and Read

    [Fact]
    public async Task WriteAndReadAsync_RoundTripsAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("test.txt", "hello world");

        // Act
        string? content = await this._store.ReadFileAsync("test.txt");

        // Assert
        Assert.Equal("hello world", content);
    }

    [Fact]
    public async Task WriteFileAsync_OverwritesExistingAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("test.txt", "first");
        await this._store.WriteFileAsync("test.txt", "second");

        // Act
        string? content = await this._store.ReadFileAsync("test.txt");

        // Assert
        Assert.Equal("second", content);
    }

    [Fact]
    public async Task ReadFileAsync_NonExistent_ReturnsNullAsync()
    {
        // Act
        string? content = await this._store.ReadFileAsync("missing.txt");

        // Assert
        Assert.Null(content);
    }

    #endregion

    #region Delete

    [Fact]
    public async Task DeleteFileAsync_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("delete-me.txt", "content");

        // Act
        bool deleted = await this._store.DeleteFileAsync("delete-me.txt");

        // Assert
        Assert.True(deleted);
        Assert.Null(await this._store.ReadFileAsync("delete-me.txt"));
    }

    [Fact]
    public async Task DeleteFileAsync_NonExistent_ReturnsFalseAsync()
    {
        // Act
        bool deleted = await this._store.DeleteFileAsync("nope.txt");

        // Assert
        Assert.False(deleted);
    }

    #endregion

    #region FileExists

    [Fact]
    public async Task FileExistsAsync_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("exists.txt", "content");

        // Act & Assert
        Assert.True(await this._store.FileExistsAsync("exists.txt"));
    }

    [Fact]
    public async Task FileExistsAsync_NonExistent_ReturnsFalseAsync()
    {
        // Act & Assert
        Assert.False(await this._store.FileExistsAsync("missing.txt"));
    }

    #endregion

    #region ListFiles

    [Fact]
    public async Task ListFilesAsync_ReturnsDirectChildrenOnlyAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("root.txt", "content");
        await this._store.WriteFileAsync("sub/nested.txt", "content");

        // Act
        var files = await this._store.ListFilesAsync("");

        // Assert
        Assert.Single(files);
        Assert.Equal("root.txt", files[0]);
    }

    [Fact]
    public async Task ListFilesAsync_SubDirectory_ReturnsChildrenAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("sub/a.txt", "content");
        await this._store.WriteFileAsync("sub/b.txt", "content");
        await this._store.WriteFileAsync("other.txt", "content");

        // Act
        var files = await this._store.ListFilesAsync("sub");

        // Assert
        Assert.Equal(2, files.Count);
        Assert.Contains("a.txt", files);
        Assert.Contains("b.txt", files);
    }

    [Fact]
    public async Task ListFilesAsync_NonExistentDirectory_ReturnsEmptyAsync()
    {
        // Act
        var files = await this._store.ListFilesAsync("no-such-dir");

        // Assert
        Assert.Empty(files);
    }

    #endregion

    #region CreateDirectory

    [Fact]
    public async Task CreateDirectoryAsync_CreatesOnDiskAsync()
    {
        // Act
        await this._store.CreateDirectoryAsync("new-dir");

        // Assert
        Assert.True(Directory.Exists(Path.Combine(this._rootDir, "new-dir")));
    }

    #endregion

    #region SearchFiles

    [Fact]
    public async Task SearchFilesAsync_FindsMatchAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("doc.md", "This has an error on line one.\nLine two is fine.");

        // Act
        var results = await this._store.SearchFilesAsync("", "error");

        // Assert
        Assert.Single(results);
        Assert.Equal("doc.md", results[0].FileName);
        Assert.Single(results[0].MatchingLines);
        Assert.Equal(1, results[0].MatchingLines[0].LineNumber);
        Assert.Contains("error", results[0].Snippet);
    }

    [Fact]
    public async Task SearchFilesAsync_GlobFilter_ExcludesNonMatchingAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("notes.md", "important info");
        await this._store.WriteFileAsync("data.txt", "important info");

        // Act
        var results = await this._store.SearchFilesAsync("", "important", "*.md");

        // Assert
        Assert.Single(results);
        Assert.Equal("notes.md", results[0].FileName);
    }

    [Fact]
    public async Task SearchFilesAsync_NoMatch_ReturnsEmptyAsync()
    {
        // Arrange
        await this._store.WriteFileAsync("doc.md", "nothing here");

        // Act
        var results = await this._store.SearchFilesAsync("", "missing-pattern");

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task SearchFilesAsync_NonExistentDirectory_ReturnsEmptyAsync()
    {
        // Act
        var results = await this._store.SearchFilesAsync("no-dir", "anything");

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task SearchFilesAsync_RegexTimeout_ThrowsOnBadPatternAsync()
    {
        // Arrange — write a file with content that triggers catastrophic backtracking.
        // The pattern (a+)+$ with a string of 'a's followed by 'b' forces exponential backtracking.
        await this._store.WriteFileAsync("trap.txt", new string('a', 30) + "b");

        // Act & Assert — a known ReDoS pattern with backtracking
        await Assert.ThrowsAsync<RegexMatchTimeoutException>(() =>
            this._store.SearchFilesAsync("", "(a+)+$"));
    }

    #endregion
}
