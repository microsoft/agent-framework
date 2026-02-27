// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Discovers, parses, and validates SKILL.md files from filesystem directories.
/// </summary>
/// <remarks>
/// Searches directories recursively (up to <see cref="MaxSearchDepth"/> levels) for SKILL.md files.
/// Each file is validated for YAML frontmatter and resource integrity. Invalid skills are excluded
/// with logged warnings. Resource paths are checked against path traversal and symlink escape attacks.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed partial class FileAgentSkillLoader
{
    private const string SkillFileName = "SKILL.md";
    private const int MaxSearchDepth = 2;
    private const int MaxNameLength = 64;
    private const int MaxDescriptionLength = 1024;

    // Matches YAML frontmatter delimited by "---" lines. Group 1 = content between delimiters.
    // Multiline makes ^/$ match line boundaries; Singleline makes . match newlines across the block.
    // The \uFEFF? prefix allows an optional UTF-8 BOM that some editors prepend.
    // Example: "---\nname: foo\n---\nBody" → Group 1: "name: foo\n"
    private static readonly Regex s_frontmatterRegex = new(@"\A\uFEFF?^---\s*$(.+?)^---\s*$", RegexOptions.Multiline | RegexOptions.Singleline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches resource file references in skill markdown. Group 1 = relative file path.
    // Supports two forms:
    //   1. Markdown links: [text](path/file.ext)
    //   2. Backtick-quoted paths: `path/file.ext`
    // Supports optional ./ or ../ prefixes; excludes URLs (no ":" in the path character class).
    // Intentionally conservative: only matches paths with word characters, hyphens, dots,
    // and forward slashes. Paths with spaces or special characters are not supported.
    // Examples: [doc](refs/FAQ.md) → "refs/FAQ.md", `./scripts/run.py` → "./scripts/run.py",
    //           [p](../shared/doc.txt) → "../shared/doc.txt"
    private static readonly Regex s_resourceLinkRegex = new(@"(?:\[.*?\]\(|`)(\.?\.?/?[\w][\w\-./]*\.\w+)(?:\)|`)", RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches YAML "key: value" lines. Group 1 = key, Group 2 = quoted value, Group 3 = unquoted value.
    // Accepts single or double quotes; the lazy quantifier trims trailing whitespace on unquoted values.
    // Examples: "name: foo" → (name, _, foo), "name: 'foo bar'" → (name, foo bar, _),
    //           "description: \"A skill\"" → (description, A skill, _)
    private static readonly Regex s_yamlKeyValueRegex = new(@"^\s*(\w+)\s*:\s*(?:[""'](.+?)[""']|(.+?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Validates skill names: lowercase letters, numbers, and hyphens only; must not start or end with a hyphen.
    // Examples: "my-skill" ✓, "skill123" ✓, "-bad" ✗, "bad-" ✗, "Bad" ✗
    private static readonly Regex s_validNameRegex = new(@"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$", RegexOptions.Compiled);

    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillLoader"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    internal FileAgentSkillLoader(ILogger logger)
    {
        this._logger = logger;
    }

    /// <summary>
    /// Discovers skill directories and loads valid skills from them.
    /// </summary>
    /// <param name="skillPaths">Paths to search for skills. Each path can point to an individual skill folder or a parent folder.</param>
    /// <returns>A dictionary of loaded skills keyed by skill name.</returns>
    internal Dictionary<string, FileAgentSkill> DiscoverAndLoadSkills(IEnumerable<string> skillPaths)
    {
        var skills = new Dictionary<string, FileAgentSkill>(StringComparer.OrdinalIgnoreCase);

        var discoveredPaths = DiscoverSkillDirectories(skillPaths);

        LogSkillsDiscovered(this._logger, discoveredPaths.Count);

        foreach (string skillPath in discoveredPaths)
        {
            FileAgentSkill? skill = this.ParseSkillFile(skillPath);
            if (skill is null)
            {
                continue;
            }

            if (skills.TryGetValue(skill.Frontmatter.Name, out FileAgentSkill? existing))
            {
                LogDuplicateSkillName(this._logger, skill.Frontmatter.Name, skillPath, existing.SourcePath);

                // Skip duplicate skill names, keeping the first one found.
                continue;
            }

            skills[skill.Frontmatter.Name] = skill;

            LogSkillLoaded(this._logger, skill.Frontmatter.Name);
        }

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <summary>
    /// Reads a resource file from disk with path traversal and symlink guards.
    /// </summary>
    /// <param name="skill">The skill that owns the resource.</param>
    /// <param name="resourceName">Relative path of the resource within the skill directory.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>The UTF-8 text content of the resource file.</returns>
    /// <exception cref="InvalidOperationException">
    /// The resource is not registered, resolves outside the skill directory, or does not exist.
    /// </exception>
    public async Task<string> ReadSkillResourceAsync(FileAgentSkill skill, string resourceName, CancellationToken cancellationToken = default)
    {
        resourceName = NormalizeResourcePath(resourceName);

        if (!skill.ResourceNames.Any(r => r.Equals(resourceName, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException($"Resource '{resourceName}' not found in skill '{skill.Frontmatter.Name}'.");
        }

        string fullPath = Path.GetFullPath(Path.Combine(skill.SourcePath, resourceName));
        string normalizedSourcePath = Path.GetFullPath(skill.SourcePath) + Path.DirectorySeparatorChar;

        if (!IsPathWithinDirectory(fullPath, normalizedSourcePath))
        {
            throw new InvalidOperationException($"Resource file '{resourceName}' references a path outside the skill directory.");
        }

        if (!File.Exists(fullPath))
        {
            throw new InvalidOperationException($"Resource file '{resourceName}' not found in skill '{skill.Frontmatter.Name}'.");
        }

        if (HasSymlinkInPath(fullPath, normalizedSourcePath))
        {
            throw new InvalidOperationException($"Resource file '{resourceName}' is a symlink that resolves outside the skill directory.");
        }

        LogResourceReading(this._logger, resourceName, skill.Frontmatter.Name);

#if NET
        return await File.ReadAllTextAsync(fullPath, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
        return await Task.FromResult(File.ReadAllText(fullPath, Encoding.UTF8)).ConfigureAwait(false);
#endif
    }

    private static List<string> DiscoverSkillDirectories(IEnumerable<string> skillPaths)
    {
        var discoveredPaths = new List<string>();

        foreach (string rootDirectory in skillPaths)
        {
            if (string.IsNullOrWhiteSpace(rootDirectory) || !Directory.Exists(rootDirectory))
            {
                continue;
            }

            SearchDirectoriesForSkills(rootDirectory, discoveredPaths, currentDepth: 0);
        }

        return discoveredPaths;
    }

    private static void SearchDirectoriesForSkills(string directory, List<string> results, int currentDepth)
    {
        string skillFilePath = Path.Combine(directory, SkillFileName);
        if (File.Exists(skillFilePath))
        {
            results.Add(Path.GetFullPath(directory));
        }

        if (currentDepth >= MaxSearchDepth)
        {
            return;
        }

        foreach (string subdirectory in Directory.EnumerateDirectories(directory))
        {
            SearchDirectoriesForSkills(subdirectory, results, currentDepth + 1);
        }
    }

    private FileAgentSkill? ParseSkillFile(string skillDirectoryPath)
    {
        string skillFilePath = Path.Combine(skillDirectoryPath, SkillFileName);

        string content = File.ReadAllText(skillFilePath, Encoding.UTF8);

        if (!this.TryParseSkillDocument(content, skillFilePath, out FileAgentSkillFrontmatter frontmatter, out string body))
        {
            return null;
        }

        List<string> resourceNames = ExtractResourcePaths(body);

        if (!this.ValidateResources(skillDirectoryPath, resourceNames, frontmatter.Name))
        {
            return null;
        }

        return new FileAgentSkill(
            frontmatter: frontmatter,
            body: body,
            sourcePath: skillDirectoryPath,
            resourceNames: resourceNames);
    }

    private bool TryParseSkillDocument(string content, string skillFilePath, out FileAgentSkillFrontmatter frontmatter, out string body)
    {
        frontmatter = null!;
        body = null!;

        Match match = s_frontmatterRegex.Match(content);
        if (!match.Success)
        {
            LogInvalidFrontmatter(this._logger, skillFilePath);
            return false;
        }

        string? name = null;
        string? description = null;

        string yamlContent = match.Groups[1].Value.Trim();

        foreach (Match kvMatch in s_yamlKeyValueRegex.Matches(yamlContent))
        {
            string key = kvMatch.Groups[1].Value;
            string value = kvMatch.Groups[2].Success ? kvMatch.Groups[2].Value : kvMatch.Groups[3].Value;

            if (string.Equals(key, "name", StringComparison.OrdinalIgnoreCase))
            {
                name = value;
            }
            else if (string.Equals(key, "description", StringComparison.OrdinalIgnoreCase))
            {
                description = value;
            }
        }

        if (string.IsNullOrWhiteSpace(name))
        {
            LogMissingFrontmatterField(this._logger, skillFilePath, "name");
            return false;
        }

        if (name.Length > MaxNameLength || !s_validNameRegex.IsMatch(name))
        {
            LogInvalidFieldValue(this._logger, skillFilePath, "name", $"Must be {MaxNameLength} characters or fewer, using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen.");
            return false;
        }

        if (string.IsNullOrWhiteSpace(description))
        {
            LogMissingFrontmatterField(this._logger, skillFilePath, "description");
            return false;
        }

        if (description.Length > MaxDescriptionLength)
        {
            LogInvalidFieldValue(this._logger, skillFilePath, "description", $"Must be {MaxDescriptionLength} characters or fewer.");
            return false;
        }

        frontmatter = new FileAgentSkillFrontmatter(name, description);
        body = content.Substring(match.Index + match.Length).TrimStart();

        return true;
    }

    private bool ValidateResources(string skillDirectoryPath, List<string> resourceNames, string skillName)
    {
        string normalizedSkillPath = Path.GetFullPath(skillDirectoryPath) + Path.DirectorySeparatorChar;

        foreach (string resourceName in resourceNames)
        {
            string fullPath = Path.GetFullPath(Path.Combine(skillDirectoryPath, resourceName));

            if (!IsPathWithinDirectory(fullPath, normalizedSkillPath))
            {
                LogResourcePathTraversal(this._logger, skillName, resourceName);
                return false;
            }

            if (!File.Exists(fullPath))
            {
                LogMissingResource(this._logger, skillName, resourceName);
                return false;
            }

            if (HasSymlinkInPath(fullPath, normalizedSkillPath))
            {
                LogResourceSymlinkEscape(this._logger, skillName, resourceName);
                return false;
            }
        }

        return true;
    }

    /// <summary>
    /// Checks that <paramref name="fullPath"/> is under <paramref name="normalizedDirectoryPath"/>,
    /// guarding against path traversal attacks.
    /// </summary>
    private static bool IsPathWithinDirectory(string fullPath, string normalizedDirectoryPath)
    {
        return fullPath.StartsWith(normalizedDirectoryPath, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Checks whether any segment in <paramref name="fullPath"/> (relative to
    /// <paramref name="normalizedDirectoryPath"/>) is a symlink (reparse point).
    /// Uses <see cref="FileAttributes.ReparsePoint"/> which is available on all target frameworks.
    /// </summary>
    private static bool HasSymlinkInPath(string fullPath, string normalizedDirectoryPath)
    {
        string relativePath = fullPath.Substring(normalizedDirectoryPath.Length);
        string[] segments = relativePath.Split(
            new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar },
            StringSplitOptions.RemoveEmptyEntries);

        string currentPath = normalizedDirectoryPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        foreach (string segment in segments)
        {
            currentPath = Path.Combine(currentPath, segment);

            if ((File.GetAttributes(currentPath) & FileAttributes.ReparsePoint) != 0)
            {
                return true;
            }
        }

        return false;
    }

    private static List<string> ExtractResourcePaths(string content)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var paths = new List<string>();
        foreach (Match m in s_resourceLinkRegex.Matches(content))
        {
            string path = NormalizeResourcePath(m.Groups[1].Value);
            if (seen.Add(path))
            {
                paths.Add(path);
            }
        }

        return paths;
    }

    /// <summary>
    /// Normalizes a relative resource path by trimming a leading <c>./</c> prefix and replacing
    /// backslashes with forward slashes so that <c>./refs/doc.md</c> and <c>refs/doc.md</c> are
    /// treated as the same resource.
    /// </summary>
    private static string NormalizeResourcePath(string path)
    {
        if (path.IndexOf('\\') >= 0)
        {
            path = path.Replace('\\', '/');
        }

        if (path.StartsWith("./", StringComparison.Ordinal))
        {
            path = path.Substring(2);
        }

        return path;
    }

    [LoggerMessage(LogLevel.Information, "Discovered {Count} potential skills")]
    private static partial void LogSkillsDiscovered(ILogger logger, int count);

    [LoggerMessage(LogLevel.Information, "Loaded skill: {SkillName}")]
    private static partial void LogSkillLoaded(ILogger logger, string skillName);

    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' does not contain valid YAML frontmatter delimited by '---'")]
    private static partial void LogInvalidFrontmatter(ILogger logger, string skillFilePath);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' is missing a '{FieldName}' field in frontmatter")]
    private static partial void LogMissingFrontmatterField(ILogger logger, string skillFilePath, string fieldName);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' has an invalid '{FieldName}' value: {Reason}")]
    private static partial void LogInvalidFieldValue(ILogger logger, string skillFilePath, string fieldName, string reason);

    [LoggerMessage(LogLevel.Warning, "Excluding skill '{SkillName}': referenced resource '{ResourceName}' does not exist")]
    private static partial void LogMissingResource(ILogger logger, string skillName, string resourceName);

    [LoggerMessage(LogLevel.Warning, "Excluding skill '{SkillName}': resource '{ResourceName}' references a path outside the skill directory")]
    private static partial void LogResourcePathTraversal(ILogger logger, string skillName, string resourceName);

    [LoggerMessage(LogLevel.Warning, "Duplicate skill name '{SkillName}': skill from '{NewPath}' skipped in favor of existing skill from '{ExistingPath}'")]
    private static partial void LogDuplicateSkillName(ILogger logger, string skillName, string newPath, string existingPath);

    [LoggerMessage(LogLevel.Warning, "Excluding skill '{SkillName}': resource '{ResourceName}' is a symlink that resolves outside the skill directory")]
    private static partial void LogResourceSymlinkEscape(ILogger logger, string skillName, string resourceName);

    [LoggerMessage(LogLevel.Information, "Reading resource '{FileName}' from skill '{SkillName}'")]
    private static partial void LogResourceReading(ILogger logger, string fileName, string skillName);
}
