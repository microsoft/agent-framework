// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
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
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteAsync("../escape.txt", "content"));
    }

    [Fact]
    public async Task ReadFileAsync_AbsolutePath_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.ReadAsync("/etc/passwd"));
    }

    [Fact]
    public async Task DeleteFileAsync_DriveRootedPath_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.DeleteAsync("C:\\temp\\file.txt"));
    }

    [Fact]
    public async Task WriteFileAsync_DotSegment_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteAsync("./file.txt", "content"));
    }

    [Fact]
    public async Task WriteFileAsync_DoubleDotsInFileName_AllowedAsync()
    {
        // Arrange — "notes..md" contains ".." but is not a ".." segment
        await this._store.WriteAsync("notes..md", "content");

        // Act
        string? result = await this._store.ReadAsync("notes..md");

        // Assert
        Assert.Equal("content", result);
    }

    [Fact]
    public async Task WriteFileAsync_TrailingSlash_NormalizesAsync()
    {
        // Act — trailing slash is trimmed during normalization.
        await this._store.WriteAsync("subdir/", "content");

        // Assert — the file is accessible via the normalized name.
        string? result = await this._store.ReadAsync("subdir");
        Assert.Equal("content", result);
    }

    #endregion

    #region Write and Read

    [Fact]
    public async Task WriteAndReadAsync_RoundTripsAsync()
    {
        // Arrange
        await this._store.WriteAsync("test.txt", "hello world");

        // Act
        string? content = await this._store.ReadAsync("test.txt");

        // Assert
        Assert.Equal("hello world", content);
    }

    [Fact]
    public async Task WriteFileAsync_OverwritesExistingAsync()
    {
        // Arrange
        await this._store.WriteAsync("test.txt", "first");
        await this._store.WriteAsync("test.txt", "second");

        // Act
        string? content = await this._store.ReadAsync("test.txt");

        // Assert
        Assert.Equal("second", content);
    }

    [Fact]
    public async Task ReadFileAsync_NonExistent_ReturnsNullAsync()
    {
        // Act
        string? content = await this._store.ReadAsync("missing.txt");

        // Assert
        Assert.Null(content);
    }

    #endregion

    #region Delete

    [Fact]
    public async Task DeleteFileAsync_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        await this._store.WriteAsync("delete-me.txt", "content");

        // Act
        bool deleted = await this._store.DeleteAsync("delete-me.txt");

        // Assert
        Assert.True(deleted);
        Assert.Null(await this._store.ReadAsync("delete-me.txt"));
    }

    [Fact]
    public async Task DeleteFileAsync_NonExistent_ReturnsFalseAsync()
    {
        // Act
        bool deleted = await this._store.DeleteAsync("nope.txt");

        // Assert
        Assert.False(deleted);
    }

    #endregion

    #region FileExists

    [Fact]
    public async Task FileExistsAsync_ExistingFile_ReturnsTrueAsync()
    {
        // Arrange
        await this._store.WriteAsync("exists.txt", "content");

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
        await this._store.WriteAsync("root.txt", "content");
        await this._store.WriteAsync("sub/nested.txt", "content");

        // Act
        var files = (await this._store.ListChildrenAsync(""))
            .Where(e => e.Type == FileStoreEntry.File)
            .Select(e => e.Name)
            .ToList();

        // Assert
        Assert.Single(files);
        Assert.Equal("root.txt", files[0]);
    }

    [Fact]
    public async Task ListFilesAsync_SubDirectory_ReturnsChildrenAsync()
    {
        // Arrange
        await this._store.WriteAsync("sub/a.txt", "content");
        await this._store.WriteAsync("sub/b.txt", "content");
        await this._store.WriteAsync("other.txt", "content");

        // Act
        var files = (await this._store.ListChildrenAsync("sub"))
            .Where(e => e.Type == FileStoreEntry.File)
            .Select(e => e.Name)
            .ToList();

        // Assert
        Assert.Equal(2, files.Count);
        Assert.Contains("a.txt", files);
        Assert.Contains("b.txt", files);
    }

    [Fact]
    public async Task ListFilesAsync_NonExistentDirectory_ReturnsEmptyAsync()
    {
        // Act
        var files = (await this._store.ListChildrenAsync("no-such-dir"))
            .Where(e => e.Type == FileStoreEntry.File)
            .Select(e => e.Name)
            .ToList();

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
        await this._store.WriteAsync("doc.md", "This has an error on line one.\nLine two is fine.");

        // Act
        var results = await this._store.SearchAsync("", "error");

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
        await this._store.WriteAsync("notes.md", "important info");
        await this._store.WriteAsync("data.txt", "important info");

        // Act
        var results = await this._store.SearchAsync("", "important", "*.md");

        // Assert
        Assert.Single(results);
        Assert.Equal("notes.md", results[0].FileName);
    }

    [Fact]
    public async Task SearchFilesAsync_NoMatch_ReturnsEmptyAsync()
    {
        // Arrange
        await this._store.WriteAsync("doc.md", "nothing here");

        // Act
        var results = await this._store.SearchAsync("", "missing-pattern");

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task SearchFilesAsync_NonExistentDirectory_ReturnsEmptyAsync()
    {
        // Act
        var results = await this._store.SearchAsync("no-dir", "anything");

        // Assert
        Assert.Empty(results);
    }

    [Fact]
    public async Task SearchFilesAsync_RegexTimeout_ThrowsOnBadPatternAsync()
    {
        // Arrange — write a file with content that triggers catastrophic backtracking.
        // The pattern (a+)+$ with a string of 'a's followed by 'b' forces exponential backtracking.
        await this._store.WriteAsync("trap.txt", new string('a', 30) + "b");

        // Act & Assert — a known ReDoS pattern with backtracking
        await Assert.ThrowsAsync<RegexMatchTimeoutException>(() =>
            this._store.SearchAsync("", "(a+)+$"));
    }

    [Fact]
    public async Task SearchFilesAsync_Recursive_FindsDescendantsAsync()
    {
        // Arrange
        await this._store.WriteAsync("notes.md", "Match here");
        await this._store.WriteAsync("reports/q1.md", "Match here too");
        await this._store.WriteAsync("reports/2024/q2.md", "Match here as well");

        // Act
        var results = await this._store.SearchAsync("", "Match", globPattern: null, recursive: true);

        // Assert
        Assert.Equal(3, results.Count);
        var names = string.Join(",", results.Select(r => r.FileName).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal("notes.md,reports/2024/q2.md,reports/q1.md", names);
    }

    [Fact]
    public async Task SearchFilesAsync_Recursive_GlobScopesToSubtreeAsync()
    {
        // Arrange
        await this._store.WriteAsync("notes.md", "Match here");
        await this._store.WriteAsync("reports/q1.md", "Match here too");
        await this._store.WriteAsync("reports/2024/q2.md", "Match here as well");

        // Act
        var results = await this._store.SearchAsync("", "Match", globPattern: "reports/**", recursive: true);

        // Assert
        Assert.Equal(2, results.Count);
        var names = string.Join(",", results.Select(r => r.FileName).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal("reports/2024/q2.md,reports/q1.md", names);
    }

    [Fact]
    public async Task SearchFilesAsync_Recursive_GlobMatchesNestedExtensionAsync()
    {
        // Arrange
        await this._store.WriteAsync("notes.md", "Match here");
        await this._store.WriteAsync("reports/q1.txt", "Match here too");
        await this._store.WriteAsync("reports/2024/q2.md", "Match here as well");

        // Act
        var results = await this._store.SearchAsync("", "Match", globPattern: "**/*.md", recursive: true);

        // Assert
        Assert.Equal(2, results.Count);
        var names = string.Join(",", results.Select(r => r.FileName).OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal("notes.md,reports/2024/q2.md", names);
    }

    [Fact]
    public async Task ListDirectoriesAsync_ReturnsDirectChildSubdirectoriesAsync()
    {
        // Arrange
        await this._store.WriteAsync("root.md", "x");
        await this._store.WriteAsync("reports/q1.md", "x");
        await this._store.WriteAsync("reports/2024/q2.md", "x");
        await this._store.WriteAsync("images/logo.txt", "x");

        // Act
        var directories = (await this._store.ListChildrenAsync(""))
            .Where(e => e.Type == FileStoreEntry.Directory)
            .Select(e => e.Name)
            .ToList();

        // Assert
        var sorted = string.Join(",", directories.OrderBy(d => d, StringComparer.Ordinal));
        Assert.Equal("images,reports", sorted);
    }

    [Fact]
    public async Task ListDirectoriesAsync_NestedDirectory_ReturnsChildrenAsync()
    {
        // Arrange
        await this._store.WriteAsync("reports/q1.md", "x");
        await this._store.WriteAsync("reports/2024/q2.md", "x");
        await this._store.WriteAsync("reports/2025/q3.md", "x");

        // Act
        var directories = (await this._store.ListChildrenAsync("reports"))
            .Where(e => e.Type == FileStoreEntry.Directory)
            .Select(e => e.Name)
            .ToList();

        // Assert
        var sorted = string.Join(",", directories.OrderBy(d => d, StringComparer.Ordinal));
        Assert.Equal("2024,2025", sorted);
    }

    [Fact]
    public async Task ListDirectoriesAsync_NonExistentDirectory_ReturnsEmptyAsync()
    {
        // Act
        var directories = (await this._store.ListChildrenAsync("no-dir"))
            .Where(e => e.Type == FileStoreEntry.Directory)
            .Select(e => e.Name)
            .ToList();

        // Assert
        Assert.Empty(directories);
    }

    [Fact]
    public async Task ListDirectoriesAsync_DotDotSegment_ThrowsAsync()
    {
        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(() => this._store.ListChildrenAsync("../other"));
    }

    #endregion

    #region Symlink Escape Rejection

#if NET
    /// <summary>
    /// Attempts to create a file symlink. Returns false if the platform does not support
    /// symlink creation (e.g., Windows without developer mode) or if creation fails.
    /// </summary>
    private static bool TryCreateFileSymbolicLink(string linkPath, string targetPath)
    {
        try
        {
            File.CreateSymbolicLink(linkPath, targetPath);
        }
        catch (IOException)
        {
            return false;
        }

        // Verify the symlink was actually created as a reparse point.
        return File.Exists(linkPath)
            && (File.GetAttributes(linkPath) & FileAttributes.ReparsePoint) != 0;
    }

    /// <summary>
    /// Attempts to create a directory symlink. Returns false if the platform does not support
    /// symlink creation (e.g., Windows without developer mode) or if creation fails.
    /// </summary>
    private static bool TryCreateDirectorySymbolicLink(string linkPath, string targetPath)
    {
        try
        {
            Directory.CreateSymbolicLink(linkPath, targetPath);
        }
        catch (IOException)
        {
            return false;
        }

        // Verify the symlink was actually created as a reparse point.
        return Directory.Exists(linkPath)
            && (File.GetAttributes(linkPath) & FileAttributes.ReparsePoint) != 0;
    }

    [Fact]
    public async Task ReadFileAsync_SymlinkedFile_ThrowsAsync()
    {
        // Arrange — create a file outside the root and symlink to it from inside.
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_target_read_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "SECRET_OUTSIDE_ROOT");

        string linkPath = Path.Combine(this._rootDir, "leak.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return; // Cannot create symlinks in this environment; skip.
            }

            // Act & Assert — reading through the symlink should be rejected.
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.ReadAsync("leak.txt"));
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task WriteFileAsync_SymlinkedFile_ThrowsAsync()
    {
        // Arrange — create a file outside the root and symlink to it from inside.
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_target_write_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "ORIGINAL_CONTENT");

        string linkPath = Path.Combine(this._rootDir, "overwrite.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return;
            }

            // Act & Assert — writing through the symlink should be rejected.
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteAsync("overwrite.txt", "EVIL_CONTENT"));

            // Verify the outside file was NOT modified.
            Assert.Equal("ORIGINAL_CONTENT", await File.ReadAllTextAsync(outsideFile));
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task DeleteFileAsync_SymlinkedFile_ThrowsAsync()
    {
        // Arrange
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_target_delete_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "DO_NOT_DELETE");

        string linkPath = Path.Combine(this._rootDir, "trap.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.DeleteAsync("trap.txt"));

            // Verify the outside file still exists.
            Assert.True(File.Exists(outsideFile));
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task FileExistsAsync_SymlinkedFile_ThrowsAsync()
    {
        // Arrange
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_target_exists_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "EXISTS_OUTSIDE");

        string linkPath = Path.Combine(this._rootDir, "phantom.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.FileExistsAsync("phantom.txt"));
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task WriteFileAsync_DanglingSymlink_ThrowsAsync()
    {
        // Arrange — create a symlink pointing to a non-existent target.
        string nonExistentTarget = Path.Combine(Path.GetTempPath(), "dangling_target_" + Guid.NewGuid().ToString("N") + ".txt");
        string linkPath = Path.Combine(this._rootDir, "dangling.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, nonExistentTarget))
            {
                return;
            }

            // Act & Assert — even a dangling symlink must be rejected.
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteAsync("dangling.txt", "CONTENT"));

            // Verify the target was NOT created by following the dangling link.
            Assert.False(File.Exists(nonExistentTarget));
        }
        finally
        {
            // Dangling symlinks: File.Exists returns false, but the link entry still exists.
            // Use FileInfo to delete the link itself.
            var linkInfo = new FileInfo(linkPath);
            if (linkInfo.Exists || (linkInfo.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                linkInfo.Delete();
            }
        }
    }

    [Fact]
    public async Task ListFilesAsync_SymlinkedDirectory_ThrowsAsync()
    {
        // Arrange — create a directory outside root and symlink a directory inside root to it.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_dir_target_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "secret.txt"), "SECRET");

        string linkDir = Path.Combine(this._rootDir, "linked-dir");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.ListChildrenAsync("linked-dir"));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task SearchFilesAsync_SymlinkedDirectory_ThrowsAsync()
    {
        // Arrange
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_search_target_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "data.txt"), "SENSITIVE_DATA");

        string linkDir = Path.Combine(this._rootDir, "search-link");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.SearchAsync("search-link", "SENSITIVE"));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task ReadFileAsync_ThroughDirectorySymlink_ThrowsAsync()
    {
        // Arrange — directory symlink inside root pointing outside; read a file through it.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_dir_read_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "secret.txt"), "DIR_SYMLINK_SECRET");

        string linkDir = Path.Combine(this._rootDir, "linked-output");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert — reading through a directory symlink should be rejected.
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.ReadAsync("linked-output/secret.txt"));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task WriteFileAsync_ThroughDirectorySymlink_ThrowsAsync()
    {
        // Arrange — directory symlink; attempt to create/overwrite a file through it.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_dir_write_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);

        string linkDir = Path.Combine(this._rootDir, "linked-output");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.WriteAsync("linked-output/created-by-agent.txt", "CONTENT"));

            // Verify no file was created outside.
            Assert.False(File.Exists(Path.Combine(outsideDir, "created-by-agent.txt")));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task DeleteFileAsync_ThroughDirectorySymlink_ThrowsAsync()
    {
        // Arrange — directory symlink; attempt to delete a file through it.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_dir_delete_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);
        string outsideFile = Path.Combine(outsideDir, "delete-me.txt");
        File.WriteAllText(outsideFile, "DO_NOT_DELETE");

        string linkDir = Path.Combine(this._rootDir, "linked-output");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.DeleteAsync("linked-output/delete-me.txt"));

            // Verify the outside file was NOT deleted.
            Assert.True(File.Exists(outsideFile));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task CreateDirectoryAsync_ThroughDirectorySymlink_ThrowsAsync()
    {
        // Arrange — directory symlink; attempt to create a subdirectory through it.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_dir_mkdir_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);

        string linkDir = Path.Combine(this._rootDir, "linked-output");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            // Act & Assert
            await Assert.ThrowsAsync<ArgumentException>(() => this._store.CreateDirectoryAsync("linked-output/created-directory"));

            // Verify no directory was created outside.
            Assert.False(Directory.Exists(Path.Combine(outsideDir, "created-directory")));
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task SearchFilesAsync_RootWithSymlinkedFile_DoesNotLeakContentAsync()
    {
        // Arrange — symlinked file at root level; search should not return its content.
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_search_root_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "ROOT_LEVEL_SECRET_CONTENT");

        string linkPath = Path.Combine(this._rootDir, "env-link.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return;
            }

            // Also add a normal file to confirm search still works for non-symlinks.
            await this._store.WriteAsync("normal.txt", "NORMAL_CONTENT");

            // Act — search at root should skip the symlinked file.
            var results = await this._store.SearchAsync("", "SECRET_CONTENT");

            // Assert — no results from the symlinked file.
            Assert.Empty(results);
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task ListFilesAsync_RootWithSymlinkedFile_ExcludesSymlinkAsync()
    {
        // Arrange — symlinked file at root level; listing should not include it.
        string outsideFile = Path.Combine(Path.GetTempPath(), "symlink_list_root_" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outsideFile, "OUTSIDE");

        string linkPath = Path.Combine(this._rootDir, "hidden-link.txt");

        try
        {
            if (!TryCreateFileSymbolicLink(linkPath, outsideFile))
            {
                return;
            }

            // Also add a normal file.
            await this._store.WriteAsync("visible.txt", "VISIBLE");

            // Act
            var files = (await this._store.ListChildrenAsync(""))
                .Where(e => e.Type == FileStoreEntry.File)
                .Select(e => e.Name)
                .ToList();

            // Assert — symlinked file should not appear in listing.
            Assert.DoesNotContain("hidden-link.txt", files);
            Assert.Contains("visible.txt", files);
        }
        finally
        {
            if (File.Exists(linkPath))
            {
                File.Delete(linkPath);
            }

            File.Delete(outsideFile);
        }
    }

    [Fact]
    public async Task SearchFilesAsync_Recursive_SkipsSymlinkedSubdirectoryAsync()
    {
        // Arrange — a symlinked directory under root should be skipped by recursive search.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_recursive_target_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);
        File.WriteAllText(Path.Combine(outsideDir, "leak.txt"), "RECURSIVE_SECRET_CONTENT");

        string linkDir = Path.Combine(this._rootDir, "linked-sub");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            await this._store.WriteAsync("normal/visible.txt", "RECURSIVE_VISIBLE_CONTENT");

            // Act — recursive search should not descend into the symlinked directory.
            var results = await this._store.SearchAsync("", "RECURSIVE", globPattern: null, recursive: true);

            // Assert — only the non-symlinked file is found.
            Assert.Single(results);
            Assert.Equal("normal/visible.txt", results[0].FileName);
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }

    [Fact]
    public async Task ListDirectoriesAsync_ExcludesSymlinkedDirectoryAsync()
    {
        // Arrange — a symlinked directory under root should not be listed.
        string outsideDir = Path.Combine(Path.GetTempPath(), "symlink_listdir_target_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideDir);

        string linkDir = Path.Combine(this._rootDir, "linked-listing");

        try
        {
            if (!TryCreateDirectorySymbolicLink(linkDir, outsideDir))
            {
                return;
            }

            await this._store.WriteAsync("real-dir/file.txt", "x");

            // Act
            var directories = (await this._store.ListChildrenAsync(""))
                .Where(e => e.Type == FileStoreEntry.Directory)
                .Select(e => e.Name)
                .ToList();

            // Assert — the symlinked directory is excluded, the real one is present.
            Assert.DoesNotContain("linked-listing", directories);
            Assert.Contains("real-dir", directories);
        }
        finally
        {
            if (Directory.Exists(linkDir))
            {
                Directory.Delete(linkDir);
            }

            Directory.Delete(outsideDir, recursive: true);
        }
    }
#endif

    #endregion
}
