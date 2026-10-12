// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parses the supported YAML frontmatter fields from SKILL.md content.
/// Block scalars use YAML strip (-), clip (default), and keep (+) chomping.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class AgentSkillFrontmatterParser
{
    // Case-insensitive lookup identifies known fields; values preserve the required spelling for validation.
    private static readonly Dictionary<string, string> s_frontmatterFieldNames = new(StringComparer.OrdinalIgnoreCase)
    {
        ["name"] = "name",
        ["description"] = "description",
        ["license"] = "license",
        ["compatibility"] = "compatibility",
        ["metadata"] = "metadata",
        ["allowed-tools"] = "allowed-tools",
    };

    // Matches YAML frontmatter delimited by "---" lines. Group 1 = content between delimiters.
    // Multiline makes ^/$ match line boundaries; Singleline makes . match newlines across the block.
    // The \uFEFF? prefix allows an optional UTF-8 BOM that some editors prepend.
    private static readonly Regex s_frontmatterRegex = new(@"\A\uFEFF?---\s*$(.+?)^---\s*$", RegexOptions.Multiline | RegexOptions.Singleline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches top-level YAML "key: value" lines. Group 1 = key (including quotes),
    // Group 2 = quoted value, Group 3 = unquoted value (possibly empty for keys such as "metadata:").
    // A value may start on a later indented line, but cannot consume another top-level field.
    private static readonly Regex s_yamlKeyValueRegex = new(@"^([\w-]+|""[\w-]+""|'[\w-]+')[ \t]*:[ \t]*(?:\r?\n(?:[ \t]*\r?\n)*[ \t]+)?(?:[""']([^\r\n]+?)[""']|([^\r\n]*?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches a metadata block, allowing quotes around the root key.
    // Group 1 captures the entire indented block beneath the metadata key.
    private static readonly Regex s_yamlMetadataBlockRegex = new(@"^(?:metadata|""metadata""|'metadata')\s*:\s*$\n((?:[ \t]+\S.*\n?)+)", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches indented YAML "key: value" lines within a metadata block.
    // Group 1 = key (supports hyphens), Group 2 = quoted value, Group 3 = unquoted value.
    private static readonly Regex s_yamlIndentedKeyValueRegex = new(@"^\s+([\w-]+)\s*:\s*(?:[""'](.+?)[""']|(.+?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    /// <summary>
    /// Parses frontmatter, logging diagnostics against the supplied file path or resource URI.
    /// </summary>
    /// <param name="content">The complete SKILL.md content.</param>
    /// <param name="skillLocation">The file path or resource URI used in diagnostics.</param>
    /// <param name="logger">The caller's logger.</param>
    /// <param name="frontmatter">The parsed frontmatter when parsing succeeds.</param>
    /// <returns>Whether the content contains valid supported frontmatter.</returns>
    internal static bool TryParse(string content, string skillLocation, ILogger logger, [NotNullWhen(true)] out AgentSkillFrontmatter? frontmatter)
    {
        frontmatter = null;

        Match match = s_frontmatterRegex.Match(content);
        if (!match.Success)
        {
            LogInvalidFrontmatter(logger, skillLocation);
            return false;
        }

        // Trailing blank lines are significant for block-scalar chomping.
        string yamlContent = match.Groups[1].Value.TrimStart();

        string? name = null;
        string? description = null;
        string? license = null;
        string? compatibility = null;
        string? allowedTools = null;

        // Recognized fields use exact lowercase names, with optional quotes. Reject casing variants and
        // duplicates rather than silently changing which value the skill exposes.
        var seenFields = new HashSet<string>(StringComparer.Ordinal);
        foreach (Match kvMatch in s_yamlKeyValueRegex.Matches(yamlContent))
        {
            string key = kvMatch.Groups[1].Value;
            key = key[0] is '"' or '\'' ? key.Substring(1, key.Length - 2) : key;

            // Unknown fields are intentionally excluded from this validation for forward compatibility.
            if (!s_frontmatterFieldNames.TryGetValue(key, out string? canonicalKey))
            {
                continue;
            }

            if (!string.Equals(key, canonicalKey, StringComparison.Ordinal))
            {
                LogIncorrectlyCasedFrontmatterField(logger, skillLocation, key, canonicalKey);
                return false;
            }

            if (!seenFields.Add(key))
            {
                LogDuplicateFrontmatterField(logger, skillLocation, key);
                return false;
            }

            // Empty declarations participate in key validation, but leave optional scalar fields unset.
            if (!kvMatch.Groups[2].Success && kvMatch.Groups[3].Length == 0)
            {
                continue;
            }

            string value = kvMatch.Groups[2].Success
                ? kvMatch.Groups[2].Value
                : ParseYamlScalarValue(yamlContent, kvMatch);

            if (string.Equals(key, "name", StringComparison.Ordinal))
            {
                name = value;
            }
            else if (string.Equals(key, "description", StringComparison.Ordinal))
            {
                description = value;
            }
            else if (string.Equals(key, "license", StringComparison.Ordinal))
            {
                license = value;
            }
            else if (string.Equals(key, "compatibility", StringComparison.Ordinal))
            {
                compatibility = value;
            }
            else if (string.Equals(key, "allowed-tools", StringComparison.Ordinal))
            {
                allowedTools = value;
            }
        }

        // Parse metadata block (indented key-value pairs under "metadata:").
        AdditionalPropertiesDictionary? metadata = null;
        Match metadataMatch = s_yamlMetadataBlockRegex.Match(yamlContent);
        if (metadataMatch.Success)
        {
            metadata = [];
            foreach (Match kvMatch in s_yamlIndentedKeyValueRegex.Matches(metadataMatch.Groups[1].Value))
            {
                string key = kvMatch.Groups[1].Value;
                string value = kvMatch.Groups[2].Success ? kvMatch.Groups[2].Value : kvMatch.Groups[3].Value;

                // Keep the first value and key spelling using the dictionary's case-insensitive comparison.
                if (!metadata.TryAdd(key, value))
                {
                    LogDuplicateMetadataKey(logger, skillLocation, key);
                }
            }
        }

        if (!AgentSkillFrontmatter.ValidateName(name, out string? validationReason) ||
            !AgentSkillFrontmatter.ValidateDescription(description, out validationReason) ||
            !AgentSkillFrontmatter.ValidateCompatibility(compatibility, out validationReason))
        {
            LogInvalidFieldValue(logger, skillLocation, "frontmatter", validationReason);
            return false;
        }

        frontmatter = new AgentSkillFrontmatter(name!, description!, compatibility)
        {
            License = license,
            AllowedTools = allowedTools,
            Metadata = metadata,
        };

        return true;
    }

    private static string ParseYamlScalarValue(string yamlContent, Match kvMatch)
    {
        string value = kvMatch.Groups[3].Value;

        if (value.Length == 0 || value[0] is not ('|' or '>'))
        {
            return value;
        }

        char scalarStyle = value[0];
        // YAML allows the indentation indicator before or after the chomping indicator.
        int chompingIndex = value.Length > 1 && value[1] is >= '1' and <= '9' ? 2 : 1;
        char chompingIndicator = value.Length > chompingIndex ? value[chompingIndex] : '\0';

        int nextLineStart = yamlContent.IndexOf('\n', kvMatch.Groups[3].Index + kvMatch.Groups[3].Length);
        if (nextLineStart < 0)
        {
            return value;
        }

        nextLineStart++;

        var blockLines = new List<string>();
        using var reader = new StringReader(yamlContent.Substring(nextLineStart));

        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                blockLines.Add(string.Empty);
                continue;
            }

            if (line[0] != ' ' && line[0] != '\t')
            {
                break;
            }

            blockLines.Add(line);
        }

        if (blockLines.Count == 0)
        {
            return string.Empty;
        }

        int commonIndent = blockLines
            .Where(line => line.Length > 0)
            .Select(line => line.TakeWhile(ch => ch == ' ' || ch == '\t').Count())
            .DefaultIfEmpty(0)
            .Min();

        string[] normalizedLines = blockLines
            .Select(line => line.Length == 0 ? string.Empty : line.Substring(Math.Min(commonIndent, line.Length)))
            .ToArray();

        int contentLineCount = normalizedLines.Length;
        while (contentLineCount > 0 && normalizedLines[contentLineCount - 1].Length == 0)
        {
            contentLineCount--;
        }

        string parsedValue = scalarStyle == '|'
            ? string.Join("\n", normalizedLines.Take(contentLineCount))
            : string.Join(" ", normalizedLines.Take(contentLineCount).Where(line => line.Length > 0));

        return chompingIndicator switch
        {
            '-' => parsedValue,
            '+' => parsedValue + new string('\n', normalizedLines.Length - contentLineCount + (contentLineCount > 0 ? 1 : 0)),
            _ => contentLineCount > 0 ? parsedValue + "\n" : string.Empty,
        };
    }

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' does not contain valid YAML frontmatter delimited by '---'")]
    private static partial void LogInvalidFrontmatter(ILogger logger, string skillFilePath);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' has an invalid '{FieldName}' value: {Reason}")]
    private static partial void LogInvalidFieldValue(ILogger logger, string skillFilePath, string fieldName, string reason);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' contains duplicate frontmatter field '{FieldName}'")]
    private static partial void LogDuplicateFrontmatterField(ILogger logger, string skillFilePath, string fieldName);

    [LoggerMessage(LogLevel.Warning, "SKILL.md at '{SkillFilePath}' contains duplicate metadata key '{Key}'; keeping the first value")]
    private static partial void LogDuplicateMetadataKey(ILogger logger, string skillFilePath, string key);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' uses incorrectly cased frontmatter field '{FieldName}'; expected '{ExpectedFieldName}'")]
    private static partial void LogIncorrectlyCasedFrontmatterField(ILogger logger, string skillFilePath, string fieldName, string expectedFieldName);
}
