// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill source that discovers skills from filesystem directories containing SKILL.md files.
/// </summary>
/// <remarks>
/// Searches directories recursively (up to 2 levels deep) for SKILL.md files.
/// Each file is validated for YAML frontmatter. Resource and script files are discovered by scanning the skill
/// directory for files with matching extensions. Invalid resources are skipped with logged warnings.
/// Resource and script paths are checked against path traversal and symlink escape attacks.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed partial class AgentFileSkillsSource : AgentSkillsSource
{
    private const string SkillFileName = "SKILL.md";
    private const int MaxSearchDepth = 2;

    private static readonly string[] s_defaultScriptExtensions = [".py", ".js", ".sh", ".ps1", ".cs", ".csx"];
    private static readonly string[] s_defaultResourceExtensions = [".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt"];

    // Matches YAML frontmatter delimited by "---" lines. Group 1 = content between delimiters.
    // Multiline makes ^/$ match line boundaries; Singleline makes . match newlines across the block.
    // The \uFEFF? prefix allows an optional UTF-8 BOM that some editors prepend.
    private static readonly Regex s_frontmatterRegex = new(@"\A\uFEFF?^---\s*$(.+?)^---\s*$", RegexOptions.Multiline | RegexOptions.Singleline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches top-level YAML "key: value" lines. Group 1 = key (supports hyphens for keys like allowed-tools),
    // Group 2 = quoted value, Group 3 = unquoted value.
    // Accepts single or double quotes; the lazy quantifier trims trailing whitespace on unquoted values.
    private static readonly Regex s_yamlKeyValueRegex = new(@"^([\w-]+)\s*:\s*(?:[""'](.+?)[""']|(.+?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches a "metadata:" line followed by indented sub-key/value pairs.
    // Group 1 captures the entire indented block beneath the metadata key.
    private static readonly Regex s_yamlMetadataBlockRegex = new(@"^metadata\s*:\s*$\n((?:[ \t]+\S.*\n?)+)", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    // Matches indented YAML "key: value" lines within a metadata block.
    // Group 1 = key (supports hyphens), Group 2 = quoted value, Group 3 = unquoted value.
    private static readonly Regex s_yamlIndentedKeyValueRegex = new(@"^\s+([\w-]+)\s*:\s*(?:[""'](.+?)[""']|(.+?))\s*$", RegexOptions.Multiline | RegexOptions.Compiled, TimeSpan.FromSeconds(5));

    private readonly IEnumerable<string> _skillPaths;
    private readonly HashSet<string> _allowedResourceExtensions;
    private readonly HashSet<string> _allowedScriptExtensions;
    private readonly AgentFileSkillScriptRunner? _scriptRunner;
    private readonly ILogger _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillsSource"/> class.
    /// </summary>
    /// <param name="skillPath">Path to search for skills.</param>
    /// <param name="scriptRunner">Optional runner for file-based scripts. Required only when skills contain scripts.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentFileSkillsSource(
        string skillPath,
        AgentFileSkillScriptRunner? scriptRunner = null,
        AgentFileSkillsSourceOptions? options = null,
        ILoggerFactory? loggerFactory = null)
        : this([skillPath], scriptRunner, options, loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillsSource"/> class.
    /// </summary>
    /// <param name="skillPaths">Paths to search for skills.</param>
    /// <param name="scriptRunner">Optional runner for file-based scripts. Required only when skills contain scripts.</param>
    /// <param name="options">Optional options that control skill discovery behavior.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentFileSkillsSource(
        IEnumerable<string> skillPaths,
        AgentFileSkillScriptRunner? scriptRunner = null,
        AgentFileSkillsSourceOptions? options = null,
        ILoggerFactory? loggerFactory = null)
    {
        this._skillPaths = Throw.IfNull(skillPaths);

        var resolvedOptions = options ?? new AgentFileSkillsSourceOptions();

        ValidateExtensions(resolvedOptions.AllowedResourceExtensions);
        ValidateExtensions(resolvedOptions.AllowedScriptExtensions);

        this._allowedResourceExtensions = new HashSet<string>(
            resolvedOptions.AllowedResourceExtensions ?? s_defaultResourceExtensions,
            StringComparer.OrdinalIgnoreCase);

        this._allowedScriptExtensions = new HashSet<string>(
            resolvedOptions.AllowedScriptExtensions ?? s_defaultScriptExtensions,
            StringComparer.OrdinalIgnoreCase);

        this._scriptRunner = scriptRunner;
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<AgentFileSkillsSource>();
    }

    /// <inheritdoc/>
    public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        var discoveredPaths = DiscoverSkillDirectories(this._skillPaths);

        LogSkillsDiscovered(this._logger, discoveredPaths.Count);

        var skills = new List<AgentSkill>();

        foreach (string skillPath in discoveredPaths)
        {
            AgentFileSkill? skill = this.ParseSkillDirectory(skillPath);
            if (skill is null)
            {
                continue;
            }

            skills.Add(skill);

            LogSkillLoaded(this._logger, skill.Frontmatter.Name);
        }

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return Task.FromResult(skills as IList<AgentSkill>);
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

    private AgentFileSkill? ParseSkillDirectory(string skillDirectoryFullPath)
    {
        string skillFilePath = Path.Combine(skillDirectoryFullPath, SkillFileName);
        string content = File.ReadAllText(skillFilePath, Encoding.UTF8);

        if (!this.TryParseFrontmatter(content, skillFilePath, out AgentSkillFrontmatter? frontmatter))
        {
            return null;
        }

        var resources = this.DiscoverResourceFiles(skillDirectoryFullPath, frontmatter.Name);
        var scripts = this.DiscoverScriptFiles(skillDirectoryFullPath, frontmatter.Name);

        return new AgentFileSkill(
            frontmatter: frontmatter,
            content: content,
            path: skillDirectoryFullPath,
            resources: resources,
            scripts: scripts);
    }

    private bool TryParseFrontmatter(string content, string skillFilePath, [NotNullWhen(true)] out AgentSkillFrontmatter? frontmatter)
    {
        frontmatter = null;

        Match match = s_frontmatterRegex.Match(content);
        if (!match.Success)
        {
            LogInvalidFrontmatter(this._logger, skillFilePath);
            return false;
        }

        string yamlContent = match.Groups[1].Value.Trim();

        string? name = null;
        string? description = null;
        string? license = null;
        string? compatibility = null;
        string? allowedTools = null;

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
            else if (string.Equals(key, "license", StringComparison.OrdinalIgnoreCase))
            {
                license = value;
            }
            else if (string.Equals(key, "compatibility", StringComparison.OrdinalIgnoreCase))
            {
                compatibility = value;
            }
            else if (string.Equals(key, "allowed-tools", StringComparison.OrdinalIgnoreCase))
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
                metadata[kvMatch.Groups[1].Value] = kvMatch.Groups[2].Success ? kvMatch.Groups[2].Value : kvMatch.Groups[3].Value;
            }
        }

        if (!AgentSkillFrontmatter.ValidateName(name, out string? validationReason) ||
            !AgentSkillFrontmatter.ValidateDescription(description, out validationReason))
        {
            LogInvalidFieldValue(this._logger, skillFilePath, "frontmatter", validationReason);
            return false;
        }

        frontmatter = new AgentSkillFrontmatter(name!, description!, compatibility)
        {
            License = license,
            AllowedTools = allowedTools,
            Metadata = metadata,
        };

        // skillFilePath is e.g. "/skills/my-skill/SKILL.md".
        // GetDirectoryName strips the filename → "/skills/my-skill".
        // GetFileName then extracts the last segment → "my-skill".
        // This gives us the skill's parent directory name to validate against the frontmatter name.
        string directoryName = Path.GetFileName(Path.GetDirectoryName(skillFilePath)) ?? string.Empty;
        if (!string.Equals(frontmatter.Name, directoryName, StringComparison.Ordinal))
        {
            if (this._logger.IsEnabled(LogLevel.Error))
            {
                LogNameDirectoryMismatch(this._logger, SanitizePathForLog(skillFilePath), frontmatter.Name, SanitizePathForLog(directoryName));
            }

            frontmatter = null;
            return false;
        }

        return true;
    }

    /// <summary>
    /// Scans a skill directory for resource files matching the configured extensions.
    /// </summary>
    /// <remarks>
    /// Recursively walks <paramref name="skillDirectoryFullPath"/> and collects files whose extension
    /// matches the allowed set, excluding <c>SKILL.md</c> itself. Each candidate
    /// is validated against path-traversal and symlink-escape checks; unsafe files are skipped with
    /// a warning.
    /// </remarks>
    private List<AgentFileSkillResource> DiscoverResourceFiles(string skillDirectoryFullPath, string skillName)
    {
        string normalizedSkillDirectoryFullPath = skillDirectoryFullPath + Path.DirectorySeparatorChar;

        var resources = new List<AgentFileSkillResource>();

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
            string resolvedFilePath = Path.GetFullPath(filePath);

            // Path containment check
            if (!resolvedFilePath.StartsWith(normalizedSkillDirectoryFullPath, StringComparison.OrdinalIgnoreCase))
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
            string relativePath = NormalizePath(resolvedFilePath.Substring(normalizedSkillDirectoryFullPath.Length));
            resources.Add(new AgentFileSkillResource(relativePath, resolvedFilePath));
        }

        return resources;
    }

    /// <summary>
    /// Scans a skill directory for script files matching the configured extensions.
    /// </summary>
    /// <remarks>
    /// Recursively walks the skill directory and collects files whose extension
    /// matches the allowed set. Each candidate is validated against path-traversal
    /// and symlink-escape checks; unsafe files are skipped with a warning.
    /// </remarks>
    private List<AgentFileSkillScript> DiscoverScriptFiles(string skillDirectoryFullPath, string skillName)
    {
        string normalizedSkillDirectoryFullPath = skillDirectoryFullPath + Path.DirectorySeparatorChar;
        var scripts = new List<AgentFileSkillScript>();

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
            // Filter by extension
            string extension = Path.GetExtension(filePath);
            if (string.IsNullOrEmpty(extension) || !this._allowedScriptExtensions.Contains(extension))
            {
                continue;
            }

            // Normalize the enumerated path to guard against non-canonical forms
            string resolvedFilePath = Path.GetFullPath(filePath);

            // Path containment check
            if (!resolvedFilePath.StartsWith(normalizedSkillDirectoryFullPath, StringComparison.OrdinalIgnoreCase))
            {
                if (this._logger.IsEnabled(LogLevel.Warning))
                {
                    LogScriptPathTraversal(this._logger, skillName, SanitizePathForLog(filePath));
                }

                continue;
            }

            // Symlink check
            if (HasSymlinkInPath(resolvedFilePath, normalizedSkillDirectoryFullPath))
            {
                if (this._logger.IsEnabled(LogLevel.Warning))
                {
                    LogScriptSymlinkEscape(this._logger, skillName, SanitizePathForLog(filePath));
                }

                continue;
            }

            // Compute relative path and normalize to forward slashes
            string relativePath = NormalizePath(resolvedFilePath.Substring(normalizedSkillDirectoryFullPath.Length));
            scripts.Add(new AgentFileSkillScript(relativePath, resolvedFilePath, this._scriptRunner));
        }

        return scripts;
    }

    /// <summary>
    /// Checks whether any segment in the path (relative to the directory) is a symlink.
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
    /// Normalizes a relative path by replacing backslashes with forward slashes
    /// and trimming a leading "./" prefix.
    /// </summary>
    private static string NormalizePath(string path)
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
    /// Replaces control characters in a file path with '?' to prevent log injection.
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
                throw new ArgumentException($"Each extension must start with '.'. Invalid value: '{ext}'", "allowedResourceExtensions");
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

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}' has an invalid '{FieldName}' value: {Reason}")]
    private static partial void LogInvalidFieldValue(ILogger logger, string skillFilePath, string fieldName, string reason);

    [LoggerMessage(LogLevel.Error, "SKILL.md at '{SkillFilePath}': skill name '{SkillName}' does not match parent directory name '{DirectoryName}'")]
    private static partial void LogNameDirectoryMismatch(ILogger logger, string skillFilePath, string skillName, string directoryName);

    [LoggerMessage(LogLevel.Warning, "Skipping resource in skill '{SkillName}': '{ResourcePath}' references a path outside the skill directory")]
    private static partial void LogResourcePathTraversal(ILogger logger, string skillName, string resourcePath);

    [LoggerMessage(LogLevel.Warning, "Skipping resource in skill '{SkillName}': '{ResourcePath}' is a symlink that resolves outside the skill directory")]
    private static partial void LogResourceSymlinkEscape(ILogger logger, string skillName, string resourcePath);

    [LoggerMessage(LogLevel.Debug, "Skipping file '{FilePath}' in skill '{SkillName}': extension '{Extension}' is not in the allowed list")]
    private static partial void LogResourceSkippedExtension(ILogger logger, string skillName, string filePath, string extension);

    [LoggerMessage(LogLevel.Warning, "Skipping script in skill '{SkillName}': '{ScriptPath}' references a path outside the skill directory")]
    private static partial void LogScriptPathTraversal(ILogger logger, string skillName, string scriptPath);

    [LoggerMessage(LogLevel.Warning, "Skipping script in skill '{SkillName}': '{ScriptPath}' is a symlink that resolves outside the skill directory")]
    private static partial void LogScriptSymlinkEscape(ILogger logger, string skillName, string scriptPath);
}
