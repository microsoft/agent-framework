// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal helpers shared by <see cref="FileAccessProvider"/> and <see cref="FileMemoryProvider"/>
/// for the <c>replace</c> and <c>replace_lines</c> tools.
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
        }

        foreach (FileLineEdit edit in edits)
        {
            // An empty replacement removes the line (content and its line break); otherwise the
            // replacement is written verbatim, so the caller controls any trailing newline.
            lines[edit.LineNumber - 1] = edit.NewLine;
        }

        return string.Concat(lines);
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
    private static List<string> SplitLinesKeepEnds(string content)
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
