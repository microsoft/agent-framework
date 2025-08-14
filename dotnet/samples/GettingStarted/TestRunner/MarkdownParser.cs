// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;

namespace GettingStarted.TestRunner;

/// <summary>
/// Service for parsing Markdown content and extracting information.
/// </summary>
public static partial class MarkdownParser
{
    private static readonly char[] NewlineSeparator = { '\n' };

    /// <summary>
    /// Parses markdown content and extracts the main title (first # header).
    /// </summary>
    public static string ParseReadmeTitle(string markdownContent)
    {
        if (string.IsNullOrWhiteSpace(markdownContent))
        {
            return string.Empty;
        }

        // Split into lines and find the first line that starts with #
        var lines = markdownContent.Split(NewlineSeparator, StringSplitOptions.RemoveEmptyEntries);

        foreach (var line in lines)
        {
            var trimmedLine = line.Trim();
            if (trimmedLine.StartsWith("# ", StringComparison.Ordinal))
            {
                // Extract the title text after "# " and clean it
                var title = trimmedLine.Substring(2).Trim();
                return CleanMarkdownText(title);
            }
        }

        return string.Empty;
    }

    /// <summary>
    /// Extracts folder description from README.md content.
    /// Looks for content between the first header and the next header or end of file.
    /// </summary>
    public static string ExtractFolderDescription(string markdownContent)
    {
        if (string.IsNullOrWhiteSpace(markdownContent))
        {
            return string.Empty;
        }

        var lines = markdownContent.Split('\n');
        var descriptionLines = new List<string>();
        var foundFirstHeader = false;
        var foundSecondHeader = false;

        foreach (var line in lines)
        {
            var trimmedLine = line.Trim();

            // Skip empty lines at the beginning
            if (!foundFirstHeader && string.IsNullOrWhiteSpace(trimmedLine))
            {
                continue;
            }

            // Check if this is a header line
#if NET8_0_OR_GREATER
            if (trimmedLine.StartsWith('#'))
#else
            if (trimmedLine.StartsWith("#", StringComparison.Ordinal))
#endif
            {
                if (!foundFirstHeader)
                {
                    foundFirstHeader = true;
                    continue; // Skip the first header line itself
                }

                foundSecondHeader = true;
                break; // Stop at the second header
            }

            // If we've found the first header but not the second, collect description lines
            if (foundFirstHeader && !foundSecondHeader)
            {
                // Skip empty lines immediately after the header
                if (descriptionLines.Count == 0 && string.IsNullOrWhiteSpace(trimmedLine))
                {
                    continue;
                }

                descriptionLines.Add(line);
            }
        }

        if (descriptionLines.Count == 0)
        {
            return string.Empty;
        }

        // Join the lines and clean up the markdown
        var description = string.Join("\n", descriptionLines).Trim();
        return CleanMarkdownText(description);
    }

    /// <summary>
    /// Cleans markdown text by removing formatting and converting to plain text.
    /// </summary>
    public static string CleanMarkdownText(string markdownText)
    {
        if (string.IsNullOrWhiteSpace(markdownText))
        {
            return string.Empty;
        }

        var cleaned = markdownText;

        // Remove bold formatting (**text** or __text__)
        cleaned = MarkdownRemoveBold().Replace(cleaned, "$1");

        // Remove italic formatting (*text* or _text_)
        cleaned = MarkdownRemoveItalic().Replace(cleaned, "$1");

        // Remove links [text](url) -> text
        cleaned = MarkdownRemoveLinks().Replace(cleaned, "$1");

        // Remove inline code `text` -> text
        cleaned = MarkdownRemoveCode().Replace(cleaned, "$1");

        // Remove strikethrough ~~text~~ -> text
        cleaned = MarkdownRemoveStrikethrough().Replace(cleaned, "$1");

        // Remove headers (# ## ### etc.) - keep the text but remove the hash symbols
        cleaned = MarkdownRemoveHeaders().Replace(cleaned, "");

        // Remove horizontal rules (--- or ***)
        cleaned = MarkdownRemoveHorizontalRules().Replace(cleaned, "");

        // Remove blockquote markers (>)
        cleaned = MarkdownRemoveBlockquotes().Replace(cleaned, "");

        // Remove list markers (- * + or numbers)
        cleaned = MarkdownRemoveUnorderedLists().Replace(cleaned, "");
        cleaned = MarkdownRemoveOrderedLists().Replace(cleaned, "");

        // Clean up extra whitespace
        cleaned = MarkdownNormalizeWhitespace().Replace(cleaned, " ");
        cleaned = MarkdownPreserveParagraphs().Replace(cleaned, "\n\n"); // Preserve paragraph breaks
        cleaned = cleaned.Trim();

        return cleaned;
    }

    /// <summary>
    /// Extracts the title from a README.md file in the specified folder.
    /// </summary>
    public static string? ExtractReadmeTitle(string folderName)
    {
        try
        {
            // Get the directory where the executable is located
            var executablePath = System.Reflection.Assembly.GetExecutingAssembly().Location;
            var executableDirectory = Path.GetDirectoryName(executablePath);

            if (string.IsNullOrEmpty(executableDirectory))
            {
                return null;
            }

            // Navigate up to find the project directory (where the .csproj file is)
            var projectDirectory = executableDirectory;
            while (!string.IsNullOrEmpty(projectDirectory) && !File.Exists(Path.Combine(projectDirectory, "GettingStarted.csproj")))
            {
                projectDirectory = Directory.GetParent(projectDirectory)?.FullName;
            }

            if (string.IsNullOrEmpty(projectDirectory))
            {
                return null;
            }

            // Construct the path to the README.md file in the specified folder
            var readmePath = Path.Combine(projectDirectory, folderName, "README.md");

            if (!File.Exists(readmePath))
            {
                return null;
            }

            // Read and parse the README.md content to extract the title
            var content = File.ReadAllText(readmePath);
            return ParseReadmeTitle(content);
        }
        catch (Exception)
        {
            // If anything goes wrong, return null to fallback to namespace
            return null;
        }
    }

    /// <summary>
    /// Extracts folder description from README.md file in the specified folder.
    /// </summary>
    public static string ExtractFolderDescriptionFromFile(string folderName)
    {
        try
        {
            // Get the directory where the executable is located
            var executablePath = System.Reflection.Assembly.GetExecutingAssembly().Location;
            var executableDirectory = Path.GetDirectoryName(executablePath);

            if (string.IsNullOrEmpty(executableDirectory))
            {
                return string.Empty;
            }

            // Navigate up to find the project directory (where the .csproj file is)
            var projectDirectory = executableDirectory;
            while (!string.IsNullOrEmpty(projectDirectory) && !File.Exists(Path.Combine(projectDirectory, "GettingStarted.csproj")))
            {
                projectDirectory = Directory.GetParent(projectDirectory)?.FullName;
            }

            if (string.IsNullOrEmpty(projectDirectory))
            {
                return string.Empty;
            }

            // Construct the path to the README.md file in the specified folder
            var readmePath = Path.Combine(projectDirectory, folderName, "README.md");

            if (!File.Exists(readmePath))
            {
                return string.Empty;
            }

            // Read and parse the README.md content to extract the description
            var content = File.ReadAllText(readmePath);
            return ExtractFolderDescription(content);
        }
        catch (Exception)
        {
            // If anything goes wrong, return empty string
            return string.Empty;
        }
    }

#if NET8_0_OR_GREATER
    [GeneratedRegex(@"\*\*(.*?)\*\*")]
    private static partial Regex MarkdownRemoveBold();

    [GeneratedRegex(@"\*(.*?)\*")]
    private static partial Regex MarkdownRemoveItalic();

    [GeneratedRegex(@"\[(.*?)\]\(.*?\)")]
    private static partial Regex MarkdownRemoveLinks();

    [GeneratedRegex("`(.*?)`")]
    private static partial Regex MarkdownRemoveCode();

    [GeneratedRegex(@"~~(.*?)~~")]
    private static partial Regex MarkdownRemoveStrikethrough();

    [GeneratedRegex(@"^#+\s*", RegexOptions.Multiline)]
    private static partial Regex MarkdownRemoveHeaders();

    [GeneratedRegex(@"^[-*]{3,}\s*$", RegexOptions.Multiline)]
    private static partial Regex MarkdownRemoveHorizontalRules();

    [GeneratedRegex(@"^>\s*", RegexOptions.Multiline)]
    private static partial Regex MarkdownRemoveBlockquotes();

    [GeneratedRegex(@"^[\s]*[-*+]\s+", RegexOptions.Multiline)]
    private static partial Regex MarkdownRemoveUnorderedLists();

    [GeneratedRegex(@"^[\s]*\d+\.\s+", RegexOptions.Multiline)]
    private static partial Regex MarkdownRemoveOrderedLists();

    [GeneratedRegex(@"\s+")]
    private static partial Regex MarkdownNormalizeWhitespace();

    [GeneratedRegex(@"\n\s*\n")]
    private static partial Regex MarkdownPreserveParagraphs();
#else
#pragma warning disable SYSLIB1045 // Use GeneratedRegexAttribute for regexes
    private static Regex MarkdownRemoveBold() => new(@"\*\*(.*?)\*\*");

    private static Regex MarkdownRemoveItalic() => new(@"\*(.*?)\*");

    private static Regex MarkdownRemoveLinks() => new(@"\[(.*?)\]\(.*?\)");

    private static Regex MarkdownRemoveCode() => new("`(.*?)`");

    private static Regex MarkdownRemoveStrikethrough() => new("~~(.*?)~~");

    private static Regex MarkdownRemoveHeaders() => new(@"^#+\s*", RegexOptions.Multiline);

    private static Regex MarkdownRemoveHorizontalRules() => new(@"^[-*]{3,}\s*$", RegexOptions.Multiline);

    private static Regex MarkdownRemoveBlockquotes() => new(@"^>\s*", RegexOptions.Multiline);

    private static Regex MarkdownRemoveUnorderedLists() => new(@"^[\s]*[-*+]\s+", RegexOptions.Multiline);

    private static Regex MarkdownRemoveOrderedLists() => new(@"^[\s]*\d+\.\s+", RegexOptions.Multiline);

    private static Regex MarkdownNormalizeWhitespace() => new(@"\s+");

    private static Regex MarkdownPreserveParagraphs() => new(@"\n\s*\n");
#pragma warning restore SYSLIB1045
#endif
}
