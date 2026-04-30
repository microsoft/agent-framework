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
using Microsoft.Extensions.FileSystemGlobbing;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A file-system-backed implementation of <see cref="AgentFileStore"/> that stores files on disk
/// under a configurable root directory.
/// </summary>
/// <remarks>
/// <para>
/// All paths passed to this store are resolved relative to the root directory provided
/// at construction time. Lexical path traversal attempts (for example, via <c>..</c> segments
/// or absolute paths) are rejected with an <see cref="ArgumentException"/>.
/// </para>
/// <para>
/// By default, paths whose resolution traverses or terminates at a symbolic link / reparse point
/// are also rejected to prevent escaping the root via filesystem indirection. This can be disabled
/// via <see cref="FileSystemAgentFileStoreOptions.RejectSymlinks"/>.
/// </para>
/// <para>
/// An optional glob denylist (<see cref="FileSystemAgentFileStoreOptions.Denylist"/>) blocks
/// access to matching paths even when they resolve to a safe location.
/// </para>
/// <para>
/// The root directory is created automatically if it does not already exist.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemAgentFileStore : AgentFileStore
{
    /// <summary>
    /// The canonical full path of the root directory, always ending with a directory separator.
    /// </summary>
    private readonly string _rootPath;
    private readonly bool _rejectSymlinks;
    private readonly IReadOnlyList<string> _denylist;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileSystemAgentFileStore"/> class with default options.
    /// </summary>
    /// <param name="rootDirectory">
    /// The root directory under which all files are stored. Created if it does not exist.
    /// </param>
    public FileSystemAgentFileStore(string rootDirectory)
        : this(rootDirectory, options: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FileSystemAgentFileStore"/> class.
    /// </summary>
    /// <param name="rootDirectory">
    /// The root directory under which all files are stored. Created if it does not exist.
    /// </param>
    /// <param name="options">Optional settings controlling security behavior. When <see langword="null"/>, defaults are used.</param>
    public FileSystemAgentFileStore(string rootDirectory, FileSystemAgentFileStoreOptions? options)
    {
        _ = Throw.IfNullOrWhitespace(rootDirectory);

        // Canonicalize the root and ensure it ends with a separator for prefix comparison.
        string fullRoot = Path.GetFullPath(rootDirectory);
        if (!fullRoot.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal) &&
            !fullRoot.EndsWith(Path.AltDirectorySeparatorChar.ToString(), StringComparison.Ordinal))
        {
            fullRoot += Path.DirectorySeparatorChar;
        }

        this._rootPath = fullRoot;
        this._rejectSymlinks = options?.RejectSymlinks ?? true;
        this._denylist = options?.Denylist ?? [];
        Directory.CreateDirectory(fullRoot);
    }

    /// <inheritdoc />
    public override async Task WriteFileAsync(string path, string content, CancellationToken cancellationToken = default)
    {
        string fullPath = this.ResolveSafePath(path);

        // Ensure the parent directory exists.
        string? parentDir = Path.GetDirectoryName(fullPath);
        if (parentDir is not null)
        {
            Directory.CreateDirectory(parentDir);
        }

#if NET8_0_OR_GREATER
        await File.WriteAllTextAsync(fullPath, content, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
        using var writer = new StreamWriter(fullPath, false, Encoding.UTF8);
        await writer.WriteAsync(content).ConfigureAwait(false);
#endif
    }

    /// <inheritdoc />
    public override async Task<string?> ReadFileAsync(string path, CancellationToken cancellationToken = default)
    {
        string fullPath = this.ResolveSafePath(path);

        if (!File.Exists(fullPath))
        {
            return null;
        }

#if NET8_0_OR_GREATER
        return await File.ReadAllTextAsync(fullPath, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
        using var reader = new StreamReader(fullPath, Encoding.UTF8);
        return await reader.ReadToEndAsync().ConfigureAwait(false);
#endif
    }

    /// <inheritdoc />
    public override Task<bool> DeleteFileAsync(string path, CancellationToken cancellationToken = default)
    {
        string fullPath = this.ResolveSafePath(path);

        if (!File.Exists(fullPath))
        {
            return Task.FromResult(false);
        }

        File.Delete(fullPath);
        return Task.FromResult(true);
    }

    /// <inheritdoc />
    public override Task<IReadOnlyList<string>> ListFilesAsync(string directory, CancellationToken cancellationToken = default)
    {
        string fullDir = this.ResolveSafeDirectoryPath(directory);

        if (!Directory.Exists(fullDir))
        {
            return Task.FromResult<IReadOnlyList<string>>([]);
        }

        var files = Directory.GetFiles(fullDir)
            .Select(Path.GetFileName)
            .Where(name => name is not null)
            .ToList();

        return Task.FromResult<IReadOnlyList<string>>(files!);
    }

    /// <inheritdoc />
    public override Task<bool> FileExistsAsync(string path, CancellationToken cancellationToken = default)
    {
        string fullPath = this.ResolveSafePath(path);
        return Task.FromResult(File.Exists(fullPath));
    }

    /// <inheritdoc />
    public override async Task<IReadOnlyList<FileSearchResult>> SearchFilesAsync(
        string directory,
        string regexPattern,
        string? filePattern = null,
        CancellationToken cancellationToken = default)
    {
        string fullDir = this.ResolveSafeDirectoryPath(directory);

        if (!Directory.Exists(fullDir))
        {
            return [];
        }

        // Compile the regex with a timeout to guard against catastrophic backtracking (ReDoS).
        var regex = new Regex(regexPattern, RegexOptions.IgnoreCase, TimeSpan.FromSeconds(5));
        Matcher? matcher = filePattern is not null ? StorePaths.CreateGlobMatcher(filePattern) : null;
        var results = new List<FileSearchResult>();

        foreach (string filePath in Directory.GetFiles(fullDir))
        {
            string? fileName = Path.GetFileName(filePath);
            if (fileName is null)
            {
                continue;
            }

            // Apply the optional glob filter on the file name.
            if (!StorePaths.MatchesGlob(fileName, matcher))
            {
                continue;
            }

            // Read file content.
#if NET8_0_OR_GREATER
            string fileContent = await File.ReadAllTextAsync(filePath, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
            string fileContent;
            using (var reader = new StreamReader(filePath, Encoding.UTF8))
            {
                fileContent = await reader.ReadToEndAsync().ConfigureAwait(false);
            }
#endif

            // Search each line for regex matches, tracking line numbers and building a snippet.
            string[] lines = fileContent.Split('\n');
            var matchingLines = new List<FileSearchMatch>();
            string? firstSnippet = null;
            int lineStartOffset = 0;

            for (int i = 0; i < lines.Length; i++)
            {
                Match match = regex.Match(lines[i]);
                if (match.Success)
                {
                    matchingLines.Add(new FileSearchMatch { LineNumber = i + 1, Line = lines[i].TrimEnd('\r') });

                    // Build a context snippet around the first match (±50 chars).
                    if (firstSnippet is null)
                    {
                        int charIndex = lineStartOffset + match.Index;
                        int snippetStart = Math.Max(0, charIndex - 50);
                        int snippetEnd = Math.Min(fileContent.Length, charIndex + match.Value.Length + 50);
                        firstSnippet = fileContent.Substring(snippetStart, snippetEnd - snippetStart);
                    }
                }

                // Advance the offset past this line (including the '\n' separator).
                lineStartOffset += lines[i].Length + 1;
            }

            if (matchingLines.Count > 0)
            {
                results.Add(new FileSearchResult
                {
                    FileName = fileName,
                    Snippet = firstSnippet!,
                    MatchingLines = matchingLines,
                });
            }
        }

        return results;
    }

    /// <inheritdoc />
    public override Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default)
    {
        string fullPath = this.ResolveSafeDirectoryPath(path);
        Directory.CreateDirectory(fullPath);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Resolves a relative file path to a safe absolute path under the root directory.
    /// Rejects paths that would escape the root via traversal or rooted paths.
    /// </summary>
    private string ResolveSafePath(string relativePath)
    {
        // Normalize and validate the relative path (rejects rooted, traversal, etc.).
        string normalized = StorePaths.NormalizeRelativePath(relativePath);

        // Apply the optional denylist against the normalized forward-slash path.
        if (this._denylist.Count > 0)
        {
            foreach (string pattern in this._denylist)
            {
                if (FileSystemTool.MatchGlob(normalized, pattern))
                {
                    throw new ArgumentException(
                        $"Invalid path: '{relativePath}'. The path is blocked by the store's denylist.",
                        nameof(relativePath));
                }
            }
        }

        // Convert to OS-native separators before combining.
        string nativePath = normalized.Replace('/', Path.DirectorySeparatorChar);
        string combined = Path.Combine(this._rootPath, nativePath);
        string fullPath = Path.GetFullPath(combined);

        if (!fullPath.StartsWith(this._rootPath, StringComparison.Ordinal))
        {
            throw new ArgumentException(
                $"Invalid path: '{relativePath}'. The resolved path escapes the root directory.",
                nameof(relativePath));
        }

        // Reject any symlink/reparse-point in the resolved path components to prevent
        // filesystem-level escapes (e.g., a symlink under the root that points outside it).
        if (this._rejectSymlinks && FileSystemPathSecurity.HasSymlinkInPath(fullPath, this._rootPath))
        {
            throw new ArgumentException(
                $"Invalid path: '{relativePath}'. The path traverses or terminates at a symbolic link.",
                nameof(relativePath));
        }

        return fullPath;
    }

    /// <summary>
    /// Resolves a relative directory path to a safe absolute path under the root directory.
    /// An empty string resolves to the root directory itself.
    /// </summary>
    private string ResolveSafeDirectoryPath(string relativeDirectory)
    {
        if (string.IsNullOrEmpty(relativeDirectory))
        {
            return this._rootPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }

        return this.ResolveSafePath(relativeDirectory);
    }
}
