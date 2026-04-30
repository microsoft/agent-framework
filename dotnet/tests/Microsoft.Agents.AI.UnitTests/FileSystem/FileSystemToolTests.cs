// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Text;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.FileSystem;

public sealed class FileSystemToolTests : IDisposable
{
    private static readonly string[] s_expectedToolNames = ["fs_view", "fs_create", "fs_edit", "fs_multi_edit", "fs_glob", "fs_grep", "fs_list_dir", "fs_delete", "fs_move", "fs_rename"];
    private static readonly string[] s_expectedPythonMatches = ["a.py", "src/b.py"];

    private readonly string _root;

    public FileSystemToolTests()
    {
        this._root = Path.Combine(Path.GetTempPath(), "filesystem-tool-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(this._root);
    }

    public void Dispose()
    {
        if (Directory.Exists(this._root))
        {
            Directory.Delete(this._root, recursive: true);
        }
    }

    [Fact]
    public void Constructor_WithMissingRoot_Throws()
    {
        // Arrange
        string missing = Path.Combine(this._root, "missing");

        // Act/Assert
        Assert.Throws<ArgumentException>(() => new FileSystemTool(missing));
    }

    [Fact]
    public void Constructor_WithFileRoot_Throws()
    {
        // Arrange
        string file = this.Write("root.txt", "x");

        // Act/Assert
        Assert.Throws<ArgumentException>(() => new FileSystemTool(file));
    }

    [Fact]
    public void AsTools_ReturnsExpectedTools_WithDestructiveApproval()
    {
        // Arrange
        var tool = new FileSystemTool(this._root);

        // Act
        var tools = tool.AsTools();

        // Assert
        Assert.Equal(10, tools.Count);
        Assert.Equal(s_expectedToolNames, tools.Select(t => t.Name));
        Assert.All(tools.Take(7), t => Assert.IsNotType<ApprovalRequiredAIFunction>(t));
        Assert.All(tools.Skip(7), t => Assert.IsType<ApprovalRequiredAIFunction>(t));
    }

    [Fact]
    public void Sandbox_RejectsDotDotTraversal()
    {
        // Arrange
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<FileSystemSecurityException>(() => tool.View("..\\secret.txt"));
    }

    [Fact]
    public void Sandbox_RejectsAbsoluteOutsideRoot()
    {
        // Arrange
        var tool = new FileSystemTool(this._root);
        string outside = Path.Combine(Path.GetTempPath(), "outside-" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(outside, "secret");
        try
        {
            // Act/Assert
            Assert.Throws<FileSystemSecurityException>(() => tool.View(outside));
        }
        finally
        {
            File.Delete(outside);
        }
    }

    [Fact]
    public void Sandbox_DenylistBlocksSensitiveFiles()
    {
        // Arrange
        this.Write(".env", "SECRET=1");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<FileSystemSecurityException>(() => tool.View(".env"));
    }

    [Fact]
    public void Sandbox_DenylistWinsOverAllowlist()
    {
        // Arrange
        this.Write(".env", "SECRET=1");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { ReadPaths = ["**"], WritePaths = ["**"] });

        // Act/Assert
        Assert.Throws<FileSystemSecurityException>(() => tool.View(".env"));
        Assert.Throws<FileSystemSecurityException>(() => tool.Edit(".env", "SECRET", "PUBLIC"));
    }

    [Fact]
    public void Sandbox_ReadAllowlistBlocksOtherPaths()
    {
        // Arrange
        this.Write("src\\ok.txt", "ok");
        this.Write("other.txt", "no");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { ReadPaths = ["src/**"] });

        // Act/Assert
        Assert.Equal("ok", tool.View("src\\ok.txt").Content);
        Assert.Throws<FileSystemSecurityException>(() => tool.View("other.txt"));
    }

    [Fact]
    public void Sandbox_WriteAllowlistBlocksOtherPaths()
    {
        // Arrange
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { WritePaths = ["src/**"] });

        // Act/Assert
        tool.Create("src\\ok.txt", "ok");
        Assert.Throws<FileSystemSecurityException>(() => tool.Create("other.txt", "no"));
    }

    [Fact]
    public void View_ReturnsRequestedLineRange()
    {
        // Arrange
        this.Write("a.txt", "one\ntwo\nthree\nfour");
        var tool = new FileSystemTool(this._root);

        // Act
        ViewResult result = tool.View("a.txt", 2, 3);

        // Assert
        Assert.Equal("two" + Environment.NewLine + "three", result.Content);
        Assert.Equal(2, result.StartLine);
        Assert.Equal(3, result.EndLine);
        Assert.Equal(4, result.TotalLines);
    }

    [Fact]
    public void View_DefaultCap_Truncates()
    {
        // Arrange
        this.Write("a.txt", "1\n2\n3");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { MaxViewLines = 2 });

        // Act
        ViewResult result = tool.View("a.txt");

        // Assert
        Assert.True(result.Truncated);
        Assert.Equal(2, result.EndLine);
    }

    [Fact]
    public void View_BinaryFile_Throws()
    {
        // Arrange
        File.WriteAllBytes(Path.Combine(this._root, "bin.dat"), [1, 0, 2]);
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<InvalidDataException>(() => tool.View("bin.dat"));
    }

    [Fact]
    public void View_MissingFile_Throws()
    {
        // Arrange
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<FileNotFoundException>(() => tool.View("missing.txt"));
    }

    [Fact]
    public void View_MaxBytes_Throws()
    {
        // Arrange
        this.Write("big.txt", "abcdef");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { MaxFileBytes = 3 });

        // Act/Assert
        Assert.Throws<InvalidDataException>(() => tool.View("big.txt"));
    }

    [Fact]
    public void Create_SucceedsAndReportsBytes()
    {
        // Arrange
        var tool = new FileSystemTool(this._root);

        // Act
        CreateResult result = tool.Create("new.txt", "hello");

        // Assert
        Assert.Equal("new.txt", result.Path);
        Assert.Equal(5, result.BytesWritten);
        Assert.Equal("hello", File.ReadAllText(Path.Combine(this._root, "new.txt")));
    }

    [Fact]
    public void Create_ExistingPath_Throws()
    {
        // Arrange
        this.Write("new.txt", "old");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<IOException>(() => tool.Create("new.txt", "new"));
    }

    [Fact]
    public void Create_MaxBytes_Throws()
    {
        // Arrange
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { MaxFileBytes = 2 });

        // Act/Assert
        Assert.Throws<InvalidDataException>(() => tool.Create("new.txt", "abc"));
    }

    [Fact]
    public void Edit_UniqueMatch_Replaces()
    {
        // Arrange
        this.Write("a.txt", "hello world");
        var tool = new FileSystemTool(this._root);

        // Act
        EditResult result = tool.Edit("a.txt", "world", "there");

        // Assert
        Assert.Equal(1, result.Replacements);
        Assert.Equal("hello there", File.ReadAllText(Path.Combine(this._root, "a.txt")));
    }

    [Fact]
    public void Edit_CountParam_ReplacesExactCount()
    {
        // Arrange
        this.Write("a.txt", "x x x");
        var tool = new FileSystemTool(this._root);

        // Act
        EditResult result = tool.Edit("a.txt", "x", "y", 3);

        // Assert
        Assert.Equal(3, result.Replacements);
        Assert.Equal("y y y", File.ReadAllText(Path.Combine(this._root, "a.txt")));
    }

    [Fact]
    public void Edit_NoMatch_LeavesFileUnchanged()
    {
        // Arrange
        this.Write("a.txt", "hello");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<InvalidOperationException>(() => tool.Edit("a.txt", "missing", "x"));
        Assert.Equal("hello", File.ReadAllText(Path.Combine(this._root, "a.txt")));
    }

    [Fact]
    public void Edit_EmptyOldStr_Throws()
    {
        // Arrange
        this.Write("a.txt", "hello");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<ArgumentException>(() => tool.Edit("a.txt", string.Empty, "x"));
    }

    [Fact]
    public void MultiEdit_SequentialEdits_AppliesAtomically()
    {
        // Arrange
        this.Write("a.txt", "abc");
        var tool = new FileSystemTool(this._root);

        // Act
        MultiEditResult result = tool.MultiEdit("a.txt", [new("ab", "xy"), new("xyc", "done")]);

        // Assert
        Assert.Equal(2, result.EditsApplied);
        Assert.Equal("done", File.ReadAllText(Path.Combine(this._root, "a.txt")));
    }

    [Fact]
    public void MultiEdit_NoMatch_LeavesFileUnchanged()
    {
        // Arrange
        this.Write("a.txt", "abc");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<InvalidOperationException>(() => tool.MultiEdit("a.txt", [new("a", "b"), new("missing", "x")]));
        Assert.Equal("abc", File.ReadAllText(Path.Combine(this._root, "a.txt")));
    }

    [Fact]
    public void MultiEdit_EmptyList_Throws()
    {
        // Arrange
        this.Write("a.txt", "abc");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<ArgumentException>(() => tool.MultiEdit("a.txt", []));
    }

    [Fact]
    public void MultiEdit_InvalidOperation_Throws()
    {
        // Arrange
        this.Write("a.txt", "abc");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<ArgumentException>(() => tool.MultiEdit("a.txt", [new("", "x")]));
        Assert.Throws<ArgumentOutOfRangeException>(() => tool.MultiEdit("a.txt", [new("a", "x", 0)]));
    }

    [Fact]
    public void Glob_BasicPatternsAndRootLevelDoubleStar()
    {
        // Arrange
        this.Write("a.py", "");
        this.Write("src\\b.py", "");
        this.Write("src\\c.txt", "");
        var tool = new FileSystemTool(this._root);

        // Act
        GlobResult result = tool.Glob("**/*.py");

        // Assert
        Assert.Equal(s_expectedPythonMatches, result.Matches);
    }

    [Fact]
    public void Glob_DenylistAndScopedPath_Applies()
    {
        // Arrange
        this.Write("src\\a.txt", "");
        this.Write("other\\a.txt", "");
        this.Write("src\\.env", "secret");
        var tool = new FileSystemTool(this._root);

        // Act
        GlobResult result = tool.Glob("*.txt", "src");

        // Assert
        Assert.Equal(["src/a.txt"], result.Matches);
        Assert.DoesNotContain("src/.env", result.Matches);
    }

    [Fact]
    public void Grep_DotNetBackend_FindsRegexCaseInsensitiveAndIncludeGlob()
    {
        // Arrange
        this.Write("a.txt", "Hello\nbye");
        this.Write("a.md", "Hello");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { AllowGrepRipgrep = false });

        // Act
        GrepResult result = tool.Grep("hello", ignoreCase: true, include: "*.txt");

        // Assert
        Assert.Equal("python", result.Backend);
        GrepResult.GrepHit hit = Assert.Single(result.Hits);
        Assert.Equal("a.txt", hit.Path);
        Assert.Equal(1, hit.LineNumber);
    }

    [Fact]
    public void Grep_MaxResults_Truncates()
    {
        // Arrange
        this.Write("a.txt", "x\nx\nx");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { AllowGrepRipgrep = false, MaxResults = 2 });

        // Act
        GrepResult result = tool.Grep("x");

        // Assert
        Assert.True(result.Truncated);
        Assert.Equal(2, result.Hits.Count);
    }

    [Fact]
    public void Grep_ParseRipgrepLine_AllowsColonInPath()
    {
        // Arrange/Act
        bool parsed = FileSystemTool.TryParseRipgrepLine("C:/repo/a.txt:12:hello:world", out GrepResult.GrepHit hit);

        // Assert
        Assert.True(parsed);
        Assert.Equal("C:/repo/a.txt", hit.Path);
        Assert.Equal(12, hit.LineNumber);
        Assert.Equal("hello:world", hit.Line);
    }

    [Fact]
    public void ListDir_DepthAndDenylist_Applies()
    {
        // Arrange
        this.Write("a.txt", "");
        this.Write("dir\\b.txt", "");
        this.Write("dir\\.env", "secret");
        var tool = new FileSystemTool(this._root);

        // Act
        ListDirResult result = tool.ListDir(".", 1);

        // Assert
        Assert.Contains(result.Entries, e => e.Path == "a.txt" && e.Type == "file");
        Assert.Contains(result.Entries, e => e.Path == "dir" && e.Type == "directory");
        Assert.DoesNotContain(result.Entries, e => e.Path == "dir/b.txt");
        Assert.DoesNotContain(result.Entries, e => e.Path.EndsWith(".env", StringComparison.Ordinal));
    }

    [Fact]
    public void ListDir_MaxResults_Truncates()
    {
        // Arrange
        this.Write("a.txt", "");
        this.Write("b.txt", "");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { MaxResults = 1 });

        // Act
        ListDirResult result = tool.ListDir(".", 1);

        // Assert
        Assert.True(result.Truncated);
        Assert.Single(result.Entries);
    }

    [Fact]
    public void Delete_File_WorksAndRefusesDirectory()
    {
        // Arrange
        this.Write("a.txt", "");
        Directory.CreateDirectory(Path.Combine(this._root, "dir"));
        var tool = new FileSystemTool(this._root);

        // Act
        DeleteResult result = tool.Delete("a.txt");

        // Assert
        Assert.Equal("a.txt", result.Path);
        Assert.False(File.Exists(Path.Combine(this._root, "a.txt")));
        Assert.Throws<FileNotFoundException>(() => tool.Delete("dir"));
    }

    [Fact]
    public void Move_SuccessAndConflict()
    {
        // Arrange
        this.Write("a.txt", "a");
        this.Write("exists.txt", "x");
        var tool = new FileSystemTool(this._root);

        // Act
        MoveResult result = tool.Move("a.txt", "b.txt");

        // Assert
        Assert.Equal("a.txt", result.Source);
        Assert.Equal("b.txt", result.Destination);
        Assert.Equal("a", File.ReadAllText(Path.Combine(this._root, "b.txt")));
        Assert.Throws<IOException>(() => tool.Move("b.txt", "exists.txt"));
    }

    [Fact]
    public void Rename_SuccessAndRejectsTraversal()
    {
        // Arrange
        this.Write("a.txt", "a");
        var tool = new FileSystemTool(this._root);

        // Act
        MoveResult result = tool.Rename("a.txt", "b.txt");

        // Assert
        Assert.Equal("b.txt", result.Destination);
        Assert.Throws<FileSystemSecurityException>(() => tool.Rename("b.txt", "..\\c.txt"));
    }

    [Fact]
    public void Gitignore_SkipsByDefaultButViewStillWorks()
    {
        // Arrange
        this.Write(".gitignore", "ignored.txt\n");
        this.Write("ignored.txt", "hidden");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Empty(tool.Glob("*.txt").Matches);
        Assert.Equal("hidden", tool.View("ignored.txt").Content);
    }

    [Fact]
    public void Gitignore_CanDisable()
    {
        // Arrange
        this.Write(".gitignore", "ignored.txt\n");
        this.Write("ignored.txt", "hidden");
        var tool = new FileSystemTool(this._root, new FileSystemPolicy { RespectGitignore = false });

        // Act/Assert
        Assert.Contains("ignored.txt", tool.Glob("*.txt").Matches);
    }

    [Fact]
    public void Gitignore_NegationAndDenylistWins()
    {
        // Arrange
        this.Write(".gitignore", "*.txt\n!keep.txt\n!.env\n");
        this.Write("drop.txt", "drop");
        this.Write("keep.txt", "keep");
        this.Write(".env", "secret");
        var tool = new FileSystemTool(this._root);

        // Act
        GlobResult result = tool.Glob("*");

        // Assert
        Assert.Contains("keep.txt", result.Matches);
        Assert.DoesNotContain("drop.txt", result.Matches);
        Assert.DoesNotContain(".env", result.Matches);
    }

    [Fact]
    public void Gitignore_NestedScopedDirOnlyAndAnchored_AppliesToDiscovery()
    {
        // Arrange
        this.Write(".gitignore", "/root.txt\nbuild/\n");
        this.Write("root.txt", "x");
        this.Write("sub\\root.txt", "x");
        this.Write("build\\a.txt", "x");
        this.Write("sub\\.gitignore", "nested.txt\n");
        this.Write("sub\\nested.txt", "x");
        var tool = new FileSystemTool(this._root);

        // Act
        var matches = tool.Glob("**/*.txt").Matches;

        // Assert
        Assert.Contains("sub/root.txt", matches);
        Assert.DoesNotContain("root.txt", matches);
        Assert.DoesNotContain("build/a.txt", matches);
        Assert.DoesNotContain("sub/nested.txt", matches);
    }

    [Fact]
    public void Helper_GlobToRegex_DoubleStarMatchesRootLevel()
    {
        // Arrange
        string regex = FileSystemTool.GlobToRegex("**/*.py");

        // Act/Assert
        Assert.Matches(regex, "a.py");
        Assert.Matches(regex, "src/a.py");
    }

    [Fact]
    public void AtomicWrite_CleansTempOnEditFailure()
    {
        // Arrange
        this.Write("a.txt", "abc");
        var tool = new FileSystemTool(this._root);

        // Act/Assert
        Assert.Throws<InvalidOperationException>(() => tool.Edit("a.txt", "missing", "x"));
        Assert.Empty(Directory.EnumerateFiles(this._root, ".fstool-*"));
    }

    [Fact]
    public void SymlinkEscape_IsRejectedOrSkippedWhenUnsupported()
    {
        // Arrange
        string outside = Path.Combine(Path.GetTempPath(), "outside-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outside);
        File.WriteAllText(Path.Combine(outside, "secret.txt"), "secret");
        string link = Path.Combine(this._root, "link");
#if NET6_0_OR_GREATER
        try
        {
            Directory.CreateSymbolicLink(link, outside);
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or IOException or PlatformNotSupportedException)
        {
            Directory.Delete(outside, recursive: true);
            return;
        }

        try
        {
            var tool = new FileSystemTool(this._root);

            // Act/Assert
            Assert.Throws<FileSystemSecurityException>(() => tool.View(Path.Combine("link", "secret.txt")));
        }
        finally
        {
            Directory.Delete(outside, recursive: true);
        }
#else
        Directory.Delete(outside, recursive: true);
#endif
    }

    private string Write(string relativePath, string content)
    {
        string path = Path.Combine(this._root, relativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, content, new UTF8Encoding(false));
        return path;
    }
}
