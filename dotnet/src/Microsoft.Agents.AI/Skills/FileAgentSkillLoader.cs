// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI;

/// <summary>
/// Discovers, parses, and validates SKILL.md files from filesystem directories.
/// </summary>
/// <remarks>
/// Searches directories recursively (up to <see cref="MaxSearchDepth"/> levels) for SKILL.md files.
/// Each file is validated for YAML frontmatter. Resource files are discovered by scanning the skill
/// directory for files with matching extensions. Invalid resources are skipped with logged warnings.
/// Resource paths are checked against path traversal and symlink escape attacks.
/// </remarks>
internal sealed partial class FileAgentSkillLoader
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

    // Matches YAML "key: value" lines. Group 1 = key, Group 2 = quoted value, Group 3 = unquoted value.
    // Accepts single or double quotes; the lazy quantifier trims trailing whitespace on unquoted values.
    // Examples: "name: foo" → (name, _, foo), "name: 'foo bar'" → (name, foo bar, _),
    //           "description: \"A skill\"" → (description, A skill, _)
    private static readonly Regex s_yamlKeyValueRegex = new(@"^\s*(\w+)\s*:\s*(?:[""'](.+?)[""']|(.+?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Validates skill names: lowercase letters, numbers, and hyphens only;
    // must not start or end with a hyphen; must not contain consecutive hyphens.
    // Examples: "my-skill" ✓, "skill123" ✓, "-bad" ✗, "bad-" ✗, "Bad" ✗, "my--skill" ✗
    private static readonly Regex s_validNameRegex = new("^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$", RegexOptions.Compiled);

    private readonly ILogger _logger;
    private readonly HashSet<string> _allowedResourceExtensions;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillLoader"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="allowedResourceExtensions">File extensions to recognize as skill resources. When <see langword="null"/>, defaults are used.</param>
    internal FileAgentSkillLoader(ILogger logger, IEnumerable<string>? allowedResourceExtensions = null)
    {
        this._logger = logger;

        ValidateExtensions(allowedResourceExtensions);

        this._allowedResourceExtensions = new HashSet<string>(
            allowedResourceExtensions ?? [".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt"],
            StringComparer.OrdinalIgnoreCase);
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
    internal async Task<string> ReadSkillResourceAsync(FileAgentSkill skill, string resourceName, CancellationToken cancellationToken = default)
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

    private FileAgentSkill? ParseSkillFile(string skillDirectoryFullPath)
    {
        string skillFilePath = Path.Combine(skillDirectoryFullPath, SkillFileName);

        string content = File.ReadAllText(skillFilePath, Encoding.UTF8);

        if (!this.TryParseSkillDocument(content, skillFilePath, out SkillFrontmatter frontmatter, out string body))
        {
            return null;
        }

        List<string> resourceNames = this.DiscoverResourceFiles(skillDirectoryFullPath, frontmatter.Name);

        return new FileAgentSkill(
            frontmatter: frontmatter,
            body: body,
            sourcePath: skillDirectoryFullPath,
            resourceNames: resourceNames);
    }

    private bool TryParseSkillDocument(string content, string skillFilePath, out SkillFrontmatter frontmatter, out string body)
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
            LogInvalidFieldValue(this._logger, skillFilePath, "name", $"Must be {MaxNameLength} characters or fewer, using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen or contain consecutive hyphens.");
            return false;
        }

        // skillFilePath is e.g. "/skills/my-skill/SKILL.md".
        // GetDirectoryName strips the filename → "/skills/my-skill".
        // GetFileName then extracts the last segment → "my-skill".
        // This gives us the skill's parent directory name to validate against the frontmatter name.
        string directoryName = Path.GetFileName(Path.GetDirectoryName(skillFilePath)) ?? string.Empty;
        if (!string.Equals(name, directoryName, StringComparison.Ordinal))
        {
            if (this._logger.IsEnabled(LogLevel.Error))
            {
                LogNameDirectoryMismatch(this._logger, SanitizePathForLog(skillFilePath), name, SanitizePathForLog(directoryName));
            }

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

        frontmatter = new SkillFrontmatter(name, description);
        body = content.Substring(match.Index + match.Length).TrimStart();

        return true;
    }

    /// <summary>
    /// Scans a skill directory for resource files matching the configured extensions.
    /// </summary>
    /// <remarks>
    /// Recursively walks <paramref name="skillDirectoryFullPath"/> and collects files whose extension
    /// matches <see cref="_allowedResourceExtensions"/>, excluding <c>SKILL.md</c> itself. Each candidate
    /// is validated against path-traversal and symlink-escape checks; unsafe files are skipped with
    /// a warning.
    /// </remarks>
    private List<string> DiscoverResourceFiles(string skillDirectoryFullPath, string skillName)
    {
        string normalizedSkillDirectoryFullPath = skillDirectoryFullPath + Path.DirectorySeparatorChar;

        var resources = new List<string>();

#if NET
        var enumerationOptions = new EnumerationOptions
        {
            RecurseSubdirectories = true,
            IgnoreInaccessible = true,
            AttributesToSkip = FileAttributes.ReparsePoint,
        };

        foreach (string filePath in Directory.EnumerateFiles(skillDirectoryFullPath, "*", enumerationOptions))
#else
        foreach (string filePath in Directory.EnumerateFiles(skillDirectoryFullPath, "*", SearchOption.AllDirectories))
#endif
        {
            string fileName = Path.GetFileName(filePath);

            // Exclude SKILL.md itself
            if (string.Equals(fileName, SkillFileName, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            // Filter by extension
            string extension = Path.GetExtension(filePath);
            if (string.IsNullOrEmpty(extension) || !this._allowedResourceExtensions.Contains(extension))
            {
                if (this._logger.IsEnabled(LogLevel.Debug))
                {
                    LogResourceSkippedExtension(this._logger, skillName, SanitizePathForLog(filePath), extension);
                }
                continue;
            }

            // Normalize the enumerated path to guard against non-canonical forms
            // (redundant separators, 8.3 short names, etc.) that would produce
            // malformed relative resource names.
            string resolvedFilePath = Path.GetFullPath(filePath);

            // Path containment check
            if (!IsPathWithinDirectory(resolvedFilePath, normalizedSkillDirectoryFullPath))
            {
                if (this._logger.IsEnabled(LogLevel.Warning))
                {
                    LogResourcePathTraversal(this._logger, skillName, SanitizePathForLog(filePath));
                }
                continue;
            }

            // Symlink check
            if (HasSymlinkInPath(resolvedFilePath, normalizedSkillDirectoryFullPath))
            {
                if (this._logger.IsEnabled(LogLevel.Warning))
                {
                    LogResourceSymlinkEscape(this._logger, skillName, SanitizePathForLog(filePath));
                }
                continue;
            }

            // Compute relative path and normalize to forward slashes
            string relativePath = resolvedFilePath.Substring(normalizedSkillDirectoryFullPath.Length);
            resources.Add(NormalizeResourcePath(relativePath));
        }

        return resources;
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

    /// <summary>
    /// Replaces control characters in a file path with '?' to prevent log injection
    /// via crafted filenames (e.g., filenames containing newlines on Linux).
    /// </summary>
    private static string SanitizePathForLog(string path)
    {
        char[]? chars = null;
        for (int i = 0; i < path.Length; i++)
        {
            if (char.IsControl(path[i]))
            {
                chars ??= path.ToCharArray();
                chars[i] = '?';
            }
        }

        return chars is null ? path : new string(chars);
    }

    private static void ValidateExtensions(IEnumerable<string>? extensions)
    {
        if (extensions is null)
        {
            return;
        }

        foreach (string ext in extensions)
        {
            if (string.IsNullOrWhiteSpace(ext) || !ext.StartsWith(".", StringComparison.Ordinal))
            {
#pragma warning disable CA2208 // Instantiate argument exceptions correctly
                throw new ArgumentException($"Each extension must start with '.'. Invalid value: '{ext}'", nameof(FileAgentSkillsProviderOptions.AllowedResourceExtensions));
#pragma warning restore CA2208 // Instantiate argument exceptions correctly
            }
        }
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

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}': skill name '{SkillName}' does not match parent directory name '{DirectoryName}'")]
    private static partial void LogNameDirectoryMismatch(ILogger logger, string skillFilePath, string skillName, string directoryName);

    [LoggerMessage(LogLevel.Warning, "Skipping resource in skill '{SkillName}': '{ResourcePath}' references a path outside the skill directory")]
    private static partial void LogResourcePathTraversal(ILogger logger, string skillName, string resourcePath);

    [LoggerMessage(LogLevel.Warning, "Duplicate skill name '{SkillName}': skill from '{NewPath}' skipped in favor of existing skill from '{ExistingPath}'")]
    private static partial void LogDuplicateSkillName(ILogger logger, string skillName, string newPath, string existingPath);

    [LoggerMessage(LogLevel.Warning, "Skipping resource in skill '{SkillName}': '{ResourcePath}' is a symlink that resolves outside the skill directory")]
    private static partial void LogResourceSymlinkEscape(ILogger logger, string skillName, string resourcePath);

    [LoggerMessage(LogLevel.Information, "Reading resource '{FileName}' from skill '{SkillName}'")]
    private static partial void LogResourceReading(ILogger logger, string fileName, string skillName);

    [LoggerMessage(LogLevel.Debug, "Skipping file '{FilePath}' in skill '{SkillName}': extension '{Extension}' is not in the allowed list")]
    private static partial void LogResourceSkippedExtension(ILogger logger, string skillName, string filePath, string extension);
}
