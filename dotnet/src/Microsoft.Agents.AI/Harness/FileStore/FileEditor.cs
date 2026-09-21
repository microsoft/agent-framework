// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal helpers shared by <see cref="FileAccessProvider"/> and <see cref="FileMemoryProvider"/>
/// for the <c>replace</c>, <c>replace_lines</c>, and <c>read_lines</c> tools, and by the file stores
/// for <c>grep</c>.
/// </summary>
internal static class FileEditor
{
    /// <summary>
    /// Replaces occurrences of <paramref name="oldString"/> with <paramref name="newString"/> in
    /// <paramref name="content"/>, returning the new content and the number of replacements made.
    /// </summary>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="oldString"/> is empty, is not found, or occurs more than once
    /// while <paramref name="replaceAll"/> is <see langword="false"/>.
    /// </exception>
    internal static (string Content, int Count) ApplyReplace(string content, string oldString, string newString, bool replaceAll)
    {
        if (string.IsNullOrEmpty(oldString))
        {
            throw new ArgumentException("old_string must not be empty.");
        }

        int count = CountOccurrences(content, oldString);
        if (count == 0)
        {
            throw new ArgumentException($"old_string not found: '{oldString}'.");
        }

        if (count > 1 && !replaceAll)
        {
            throw new ArgumentException(
                $"old_string occurs {count} times; pass replace_all=true to replace all, " +
                "or provide a more specific old_string.");
        }

#if NET8_0_OR_GREATER
        return (content.Replace(oldString, newString, StringComparison.Ordinal), count);
#else
        return (content.Replace(oldString, newString), count);
#endif
    }

    /// <summary>
    /// Applies literal (1-based) line replacements to <paramref name="content"/>.
    /// </summary>
    /// <remarks>
    /// Each edit's <see cref="FileLineEdit.NewLine"/> is treated as the literal replacement text for the
    /// targeted line, including any trailing newline the caller wants to keep — the editor does not add
    /// one. An empty <see cref="FileLineEdit.NewLine"/> deletes the line entirely, including its line break.
    /// </remarks>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="edits"/> is empty, any line number is out of range, or a line number
    /// is targeted more than once.
    /// </exception>
    internal static string ApplyReplaceLines(string content, IReadOnlyList<FileLineEdit> edits)
    {
        if (edits.Count == 0)
        {
            throw new ArgumentException("At least one line edit must be provided.");
        }

        List<string> lines = SplitLinesKeepEnds(content);

        var seen = new HashSet<int>();
        foreach (FileLineEdit edit in edits)
        {
            if (!seen.Add(edit.LineNumber))
            {
                throw new ArgumentException($"Duplicate line_number {edit.LineNumber} in edits.");
            }

            if (edit.LineNumber < 1 || edit.LineNumber > lines.Count)
            {
                throw new ArgumentException(
                    $"line_number {edit.LineNumber} is out of range (file has {lines.Count} lines).");
            }

            // When the caller says what it expects to be there, a mismatch means the number is
            // stale or was never right. Refusing turns a silent overwrite of the wrong line into
            // an error, and is the one check that also covers the file changing under us.
            if (edit.ExpectedLine is not null)
            {
                string actual = TrimLineTerminator(lines[edit.LineNumber - 1]);
                if (!string.Equals(actual, TrimLineTerminator(edit.ExpectedLine), StringComparison.Ordinal))
                {
                    throw new ArgumentException(
                        $"line_number {edit.LineNumber} does not match the expected text. " +
                        "Re-read the file to get current line numbers.");
                }
            }
        }

        foreach (FileLineEdit edit in edits)
        {
            // An empty replacement removes the line (content and its line break); otherwise the
            // replacement is written verbatim, so the caller controls any trailing newline.
            lines[edit.LineNumber - 1] = edit.NewLine;
        }

        return string.Concat(lines);
    }

    /// <summary>
    /// Returns the 1-based inclusive <c>[startLine, endLine]</c> slice of <paramref name="content"/>,
    /// with each line's terminator kept attached. An <paramref name="endLine"/> past the last line is
    /// clamped, and omitting it reads to the end of the content.
    /// </summary>
    /// <exception cref="ArgumentException">
    /// Thrown when either bound is not positive, when <paramref name="endLine"/> precedes
    /// <paramref name="startLine"/>, or when <paramref name="startLine"/> is past the last line.
    /// </exception>
    internal static List<string> SliceLines(string content, int startLine, int? endLine)
    {
        List<string> lines = SplitLinesKeepEnds(content);
        int total = lines.Count;

        // These messages reach the model as the tool's failure text, so they name the arguments as the
        // generated schema exposes them (startLine/endLine), not in snake_case.
        if (startLine < 1)
        {
            throw new ArgumentException($"startLine must be a positive integer, got {startLine}.");
        }

        if (endLine is < 1)
        {
            throw new ArgumentException($"endLine must be a positive integer, got {endLine}.");
        }

        if (endLine < startLine)
        {
            throw new ArgumentException($"endLine ({endLine}) must not be less than startLine ({startLine}).");
        }

        if (startLine > total)
        {
            throw new ArgumentException($"startLine {startLine} is out of range (file has {total} lines).");
        }

        // Clamping end_line rather than failing keeps "read from here to the end" a single call.
        int lastLine = endLine is null ? total : Math.Min(endLine.Value, total);
        return lines.GetRange(startLine - 1, lastLine - startLine + 1);
    }

    /// <summary>
    /// Returns <paramref name="line"/> without its trailing <c>\r\n</c>, <c>\n</c> or lone <c>\r</c>.
    /// </summary>
    internal static string TrimLineTerminator(string line) => line.Substring(0, LineContentLength(line));

    /// <summary>
    /// Returns the length of <paramref name="line"/> up to but excluding the <c>\r\n</c>, <c>\n</c>, or
    /// lone <c>\r</c> that terminates it, so search patterns are matched against a line's text rather
    /// than its line break.
    /// </summary>
    /// <remarks>
    /// Leaving any part of the terminator in range would make an end-anchored pattern such as
    /// <c>match$</c> fail on a CRLF or lone-CR line whose text is exactly <c>match</c>. This returns a
    /// length rather than a trimmed string because the callers scan every line before knowing which ones
    /// match, and copying each one would duplicate nearly the whole file on every search.
    /// </remarks>
    internal static int LineContentLength(string line)
    {
        if (line.EndsWith("\r\n", StringComparison.Ordinal))
        {
            return line.Length - 2;
        }

        return line.EndsWith("\n", StringComparison.Ordinal) || line.EndsWith("\r", StringComparison.Ordinal)
            ? line.Length - 1
            : line.Length;
    }

    private static int CountOccurrences(string content, string value)
    {
        int count = 0;
        int index = 0;
        while ((index = content.IndexOf(value, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += value.Length;
        }

        return count;
    }

    /// <summary>
    /// Splits content into lines, keeping each line's trailing newline (<c>\r\n</c>, <c>\n</c>, or a lone
    /// <c>\r</c>) attached. The final line has no terminator when the content does not end with a newline.
    /// </summary>
    /// <remarks>
    /// This is the single definition of a "line" for the line-edit tools, so the line numbers reported by
    /// <c>grep</c> address the same lines that <c>replace_lines</c> edits. A store supplying its own
    /// <see cref="AgentFileStore.SearchAsync"/> is expected to number by this split; nothing enforces that
    /// at runtime, so an implementation that numbers differently edits the wrong line silently.
    /// </remarks>
    internal static List<string> SplitLinesKeepEnds(string content)
    {
        var lines = new List<string>();
        int start = 0;
        for (int i = 0; i < content.Length; i++)
        {
            char c = content[i];
            if (c == '\n')
            {
                lines.Add(content.Substring(start, i - start + 1));
                start = i + 1;
            }
            else if (c == '\r')
            {
                // Treat "\r\n" as a single terminator; a lone "\r" also terminates a line.
                int end = (i + 1 < content.Length && content[i + 1] == '\n') ? i + 2 : i + 1;
                lines.Add(content.Substring(start, end - start));
                i = end - 1;
                start = end;
            }
        }

        if (start < content.Length)
        {
            lines.Add(content.Substring(start));
        }

        return lines;
    }
}
