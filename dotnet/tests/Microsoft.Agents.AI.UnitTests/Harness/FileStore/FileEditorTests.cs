// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

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
}
