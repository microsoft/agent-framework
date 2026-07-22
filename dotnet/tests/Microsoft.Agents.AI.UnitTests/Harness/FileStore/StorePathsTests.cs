// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.FileSystemGlobbing;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

public class StorePathsTests
{
    #region NormalizeRelativePath — valid paths

    [Theory]
    [InlineData("file.md", "file.md")]
    [InlineData("folder/file.md", "folder/file.md")]
    [InlineData("a/b/c.txt", "a/b/c.txt")]
    public void NormalizeRelativePath_ValidPath_ReturnsNormalized(string input, string expected)
    {
        // Act
        string result = StorePaths.NormalizeRelativePath(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData("folder\\file.md", "folder/file.md")]
    [InlineData("a\\b\\c.txt", "a/b/c.txt")]
    public void NormalizeRelativePath_Backslashes_NormalizesToForwardSlash(string input, string expected)
    {
        // Act
        string result = StorePaths.NormalizeRelativePath(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData("folder//file.md", "folder/file.md")]
    [InlineData("a///b////c.txt", "a/b/c.txt")]
    public void NormalizeRelativePath_ConsecutiveSeparators_Collapsed(string input, string expected)
    {
        // Act
        string result = StorePaths.NormalizeRelativePath(input);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void NormalizeRelativePath_TrailingSlash_Trimmed()
    {
        // Act
        string result = StorePaths.NormalizeRelativePath("file.md/");

        // Assert
        Assert.Equal("file.md", result);
    }

    [Theory]
    [InlineData("/file.md")]
    [InlineData("/folder/file.md/")]
    public void NormalizeRelativePath_LeadingSlash_Throws(string input)
    {
        // Act & Assert — leading slash is treated as a rooted path.
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath(input));
    }

    #endregion

    #region NormalizeRelativePath — rejected paths

    [Theory]
    [InlineData("../file.md")]
    [InlineData("folder/../file.md")]
    [InlineData("./file.md")]
    [InlineData("folder/./file.md")]
    public void NormalizeRelativePath_TraversalSegments_Throws(string input)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath(input));
    }

    [Theory]
    [InlineData("C:\\file.md")]
    [InlineData("C:/file.md")]
    [InlineData("D:file.md")]
    public void NormalizeRelativePath_DriveRoot_Throws(string input)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath(input));
    }

    [Fact]
    public void NormalizeRelativePath_EmptyFile_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath(""));
    }

    [Fact]
    public void NormalizeRelativePath_WhitespaceOnlyFile_Throws()
    {
        // Act & Assert — whitespace-only paths are rejected as invalid file names.
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath("   "));
    }

    #endregion

    #region NormalizeRelativePath — directory mode

    [Fact]
    public void NormalizeRelativePath_EmptyDirectory_ReturnsEmpty()
    {
        // Act
        string result = StorePaths.NormalizeRelativePath("", isDirectory: true);

        // Assert
        Assert.Equal("", result);
    }

    [Theory]
    [InlineData("folder", "folder")]
    [InlineData("a/b", "a/b")]
    [InlineData("a\\b/", "a/b")]
    public void NormalizeRelativePath_DirectoryMode_NormalizesPath(string input, string expected)
    {
        // Act
        string result = StorePaths.NormalizeRelativePath(input, isDirectory: true);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void NormalizeRelativePath_DirectoryTraversal_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => StorePaths.NormalizeRelativePath("../folder", isDirectory: true));
    }

    #endregion

    #region CreateGlobMatcher and MatchesGlob

    [Theory]
    [InlineData("*.md", "notes.md", true)]
    [InlineData("*.md", "notes.txt", false)]
    [InlineData("research*", "research_results.md", true)]
    [InlineData("research*", "notes.md", false)]
    [InlineData("*.md", "NOTES.MD", true)] // case-insensitive
    public void MatchesGlob_WithMatcher_MatchesCorrectly(string pattern, string fileName, bool expected)
    {
        // Arrange
        Matcher matcher = StorePaths.CreateGlobMatcher(pattern);

        // Act
        bool result = StorePaths.MatchesGlob(fileName, matcher);

        // Assert
        Assert.Equal(expected, result);
    }

    [Fact]
    public void MatchesGlob_NullMatcher_ReturnsTrue()
    {
        // Act
        bool result = StorePaths.MatchesGlob("anything.txt", null);

        // Assert
        Assert.True(result);
    }

    #endregion
}
