// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.UnitTests.Harness.FileMemory;

/// <summary>
/// Unit tests for the <see cref="FileEditor"/> helper that backs the <c>replace</c> and
/// <c>replace_lines</c> tools.
/// </summary>
public class FileEditorTests
{
    #region ApplyReplace

    [Fact]
    public void ApplyReplace_SingleOccurrence_ReplacesAndReturnsCount()
    {
        // Act
        (string content, int count) = FileEditor.ApplyReplace("Hello world", "world", "there", replaceAll: false);

        // Assert
        Assert.Equal("Hello there", content);
        Assert.Equal(1, count);
    }

    [Fact]
    public void ApplyReplace_ReplaceAll_ReplacesEveryOccurrence()
    {
        // Act
        (string content, int count) = FileEditor.ApplyReplace("a a a", "a", "b", replaceAll: true);

        // Assert
        Assert.Equal("b b b", content);
        Assert.Equal(3, count);
    }

    [Fact]
    public void ApplyReplace_EmptyOldString_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplace("content", string.Empty, "x", replaceAll: false));
    }

    [Fact]
    public void ApplyReplace_NotFound_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplace("content", "missing", "x", replaceAll: false));
    }

    [Fact]
    public void ApplyReplace_MultipleOccurrences_WithoutReplaceAll_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplace("a a a", "a", "b", replaceAll: false));
    }

    #endregion

    #region ApplyReplaceLines

    [Fact]
    public void ApplyReplaceLines_ReplacesSpecifiedLine()
    {
        // Act — new_line is literal; the caller supplies the trailing newline to keep it.
        string result = FileEditor.ApplyReplaceLines(
            "line1\nline2\nline3",
            new List<FileLineEdit> { new() { LineNumber = 2, NewLine = "CHANGED\n" } });

        // Assert
        Assert.Equal("line1\nCHANGED\nline3", result);
    }

    [Fact]
    public void ApplyReplaceLines_EmptyEdits_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplaceLines("line1", new List<FileLineEdit>()));
    }

    [Fact]
    public void ApplyReplaceLines_OutOfRange_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplaceLines(
            "line1\nline2",
            new List<FileLineEdit> { new() { LineNumber = 5, NewLine = "X" } }));
    }

    [Fact]
    public void ApplyReplaceLines_DuplicateLineNumber_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() => FileEditor.ApplyReplaceLines(
            "line1\nline2",
            new List<FileLineEdit>
            {
                new() { LineNumber = 1, NewLine = "A" },
                new() { LineNumber = 1, NewLine = "B" },
            }));
    }

    [Fact]
    public void ApplyReplaceLines_LiteralNewLineControlsTrailingNewline()
    {
        // Act — the literal new_line keeps the trailing newline the caller provides.
        string result = FileEditor.ApplyReplaceLines(
            "line1\nline2\n",
            new List<FileLineEdit> { new() { LineNumber = 1, NewLine = "CHANGED\n" } });

        // Assert
        Assert.Equal("CHANGED\nline2\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_PreservesCrlfWhenCallerSuppliesIt()
    {
        // Act — a CRLF file keeps CRLF endings when the caller supplies "\r\n".
        string result = FileEditor.ApplyReplaceLines(
            "line1\r\nline2\r\nline3",
            new List<FileLineEdit> { new() { LineNumber = 2, NewLine = "CHANGED\r\n" } });

        // Assert
        Assert.Equal("line1\r\nCHANGED\r\nline3", result);
    }

    [Fact]
    public void ApplyReplaceLines_EmptyNewLine_DeletesMiddleLine()
    {
        // Act — an empty new_line removes the line, including its line break.
        string result = FileEditor.ApplyReplaceLines(
            "line1\nline2\nline3\n",
            new List<FileLineEdit> { new() { LineNumber = 2, NewLine = string.Empty } });

        // Assert
        Assert.Equal("line1\nline3\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_EmptyNewLine_DeletesLastLineWithoutTerminator()
    {
        // Act
        string result = FileEditor.ApplyReplaceLines(
            "line1\nline2",
            new List<FileLineEdit> { new() { LineNumber = 2, NewLine = string.Empty } });

        // Assert
        Assert.Equal("line1\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_DeleteAndReplaceInSameCall()
    {
        // Act
        string result = FileEditor.ApplyReplaceLines(
            "a\nb\nc\n",
            new List<FileLineEdit>
            {
                new() { LineNumber = 1, NewLine = string.Empty },
                new() { LineNumber = 3, NewLine = "C\n" },
            });

        // Assert
        Assert.Equal("b\nC\n", result);
    }

    [Fact]
    public void ApplyReplaceLines_EmbeddedNewLine_ExpandsIntoMultipleLines()
    {
        // Act — a literal new_line may contain its own newlines to insert extra lines.
        string result = FileEditor.ApplyReplaceLines(
            "a\nb\nc\n",
            new List<FileLineEdit> { new() { LineNumber = 2, NewLine = "b1\nb2\n" } });

        // Assert
        Assert.Equal("a\nb1\nb2\nc\n", result);
    }

    #endregion

    #region SplitLinesKeepEnds

    [Theory]
    [InlineData("a\nb\nc", new[] { "a\n", "b\n", "c" })]
    [InlineData("a\nb\n", new[] { "a\n", "b\n" })]
    [InlineData("a\r\nb\r\n", new[] { "a\r\n", "b\r\n" })]
    [InlineData("a\rb\rc", new[] { "a\r", "b\r", "c" })]
    [InlineData("a\r\nb\nc\r", new[] { "a\r\n", "b\n", "c\r" })]
    [InlineData("single", new[] { "single" })]
    [InlineData("", new string[0])]
    public void SplitLinesKeepEnds_KeepsEachLinesOwnTerminator(string content, string[] expected)
    {
        // Act
        List<string> lines = FileEditor.SplitLinesKeepEnds(content);

        // Assert
        Assert.Equal(expected, lines);
    }

    [Fact]
    public void SplitLinesKeepEnds_ConcatenationRoundTripsTheContent()
    {
        // Arrange — mixed terminators, the case a whole-file read would otherwise be needed to detect.
        const string Content = "alpha\r\nbeta\ngamma\rdelta";

        // Act
        List<string> lines = FileEditor.SplitLinesKeepEnds(Content);

        // Assert — nothing is lost or added, which is what makes a reported line reusable verbatim.
        Assert.Equal(Content, string.Concat(lines));
    }

    [Theory]
    [InlineData("match\r\n", "match")]
    [InlineData("match\n", "match")]
    [InlineData("match\r", "match")]
    [InlineData("match", "match")]
    [InlineData("", "")]
    [InlineData("a\rb\n", "a\rb")]
    public void LineContentLength_ExcludesOnlyTheTrailingTerminator(string line, string expected)
    {
        // Act
        int length = FileEditor.LineContentLength(line);

        // Assert — the length delimits exactly the line's text, which is the range searches match over.
        Assert.Equal(expected.Length, length);
        Assert.Equal(expected, line.Substring(0, length));
    }

    [Theory]
    [InlineData("beta match\r\n")]
    [InlineData("beta match\n")]
    [InlineData("beta match\r")]
    [InlineData("beta match")]
    public void LineContentLength_BoundsAnEndAnchoredMatch(string line)
    {
        // Arrange — the callers match over a range instead of a trimmed copy, so '$' has to anchor at
        // the returned length rather than at the end of the string.
        var regex = new Regex("match$", RegexOptions.IgnoreCase);

        // Act
        Match match = regex.Match(line, 0, FileEditor.LineContentLength(line));

        // Assert
        Assert.True(match.Success);
        Assert.Equal(5, match.Index);
    }

    #endregion

    #region SliceLines

    [Fact]
    public void SliceLines_ReturnsInclusiveRangeWithTerminators()
    {
        // Act
        List<string> lines = FileEditor.SliceLines("one\ntwo\nthree\nfour\n", 2, 3);

        // Assert
        Assert.Equal(2, lines.Count);
        Assert.Equal("two\nthree\n", string.Concat(lines));
    }

    [Fact]
    public void SliceLines_NullEndLine_ReadsToEndOfContent()
    {
        // Act
        List<string> lines = FileEditor.SliceLines("one\ntwo\nthree", 2, endLine: null);

        // Assert
        Assert.Equal(2, lines.Count);
        Assert.Equal("two\nthree", string.Concat(lines));
    }

    [Fact]
    public void SliceLines_EndLinePastLastLine_IsClamped()
    {
        // Act
        List<string> lines = FileEditor.SliceLines("one\ntwo\n", 1, 99);

        // Assert
        Assert.Equal(2, lines.Count);
        Assert.Equal("one\ntwo\n", string.Concat(lines));
    }

    [Theory]
    [InlineData(0, null)]
    [InlineData(-1, null)]
    [InlineData(1, 0)]
    [InlineData(3, 2)]
    [InlineData(4, null)]
    public void SliceLines_InvalidRange_Throws(int startLine, int? endLine)
    {
        // Act & Assert — "one\ntwo\nthree" has three lines.
        Assert.Throws<ArgumentException>(() => FileEditor.SliceLines("one\ntwo\nthree", startLine, endLine));
    }

    [Fact]
    public void SliceLines_EmptyContent_HasNoAddressableLines()
    {
        // Act & Assert — matches ApplyReplaceLines, which also rejects line 1 of an empty file.
        Assert.Throws<ArgumentException>(() => FileEditor.SliceLines(string.Empty, 1, null));
    }

    #endregion
}
