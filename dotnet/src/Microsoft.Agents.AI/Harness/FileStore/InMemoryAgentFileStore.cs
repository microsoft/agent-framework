// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.FileSystemGlobbing;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// An in-memory implementation of <see cref="AgentFileStore"/> that stores files in a dictionary.
/// </summary>
/// <remarks>
/// This implementation is suitable for testing and lightweight scenarios where persistence is not required.
/// Directory concepts are simulated using path prefixes — no explicit directory structure is maintained.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class InMemoryAgentFileStore : AgentFileStore
{
    private readonly ConcurrentDictionary<string, string> _files = new(StringComparer.OrdinalIgnoreCase);

    /// <inheritdoc />
    public override Task WriteAsync(string path, string content, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        this._files[path] = content;
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public override Task<string?> ReadAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        this._files.TryGetValue(path, out string? content);
        return Task.FromResult(content);
    }

    /// <inheritdoc />
    public override Task<bool> DeleteAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        return Task.FromResult(this._files.TryRemove(path, out _));
    }

    /// <inheritdoc />
    public override Task<IReadOnlyList<FileStoreEntry>> ListChildrenAsync(string directory, CancellationToken cancellationToken = default)
    {
        string prefix = StorePaths.NormalizeRelativePath(directory, isDirectory: true);
        if (prefix.Length > 0 && !prefix.EndsWith("/", StringComparison.Ordinal))
        {
            prefix += "/";
        }

        // A subdirectory is the first path segment of any key whose remainder (after the prefix)
        // still contains a separator. Collect distinct first segments, preserving original casing.
        var directories = new List<string>();
        var seenDirectories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var files = new List<string>();

        foreach (string key in this._files.Keys)
        {
            if (!key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string remainder = key.Substring(prefix.Length);
            int separatorIndex = remainder.IndexOf("/", StringComparison.Ordinal);
            if (separatorIndex < 0)
            {
                files.Add(remainder);
            }
            else if (separatorIndex > 0)
            {
                string segment = remainder.Substring(0, separatorIndex);
                if (seenDirectories.Add(segment))
                {
                    directories.Add(segment);
                }
            }
        }

        // Subdirectories first, then files.
        FileStoreEntry[] entries =
        [
            .. directories.Select(d => new FileStoreEntry(d, FileStoreEntry.Directory)),
            .. files.Select(f => new FileStoreEntry(f, FileStoreEntry.File)),
        ];

        return Task.FromResult<IReadOnlyList<FileStoreEntry>>(entries);
    }

    /// <inheritdoc />
    public override Task<bool> FileExistsAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        return Task.FromResult(this._files.ContainsKey(path));
    }

    /// <inheritdoc />
    public override Task<IReadOnlyList<FileSearchResult>> SearchAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
    {
        // Normalize the directory prefix for path matching.
        string prefix = StorePaths.NormalizeRelativePath(directory, isDirectory: true);
        if (prefix.Length > 0 && !prefix.EndsWith("/", StringComparison.Ordinal))
        {
            prefix += "/";
        }

        // Compile the regex with a timeout to guard against catastrophic backtracking (ReDoS).
        var regex = new Regex(regexPattern, RegexOptions.IgnoreCase, TimeSpan.FromSeconds(5));
        Matcher? matcher = globPattern is not null ? StorePaths.CreateGlobMatcher(globPattern) : null;
        var results = new List<FileSearchResult>();

        foreach (var kvp in this._files)
        {
            // Only consider files within the target directory (by path prefix).
            if (!kvp.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            // The file path relative to the search directory.
            string relativeName = kvp.Key.Substring(prefix.Length);

            // When not recursive, exclude files in subdirectories (direct children only).
            if (!recursive && relativeName.IndexOf("/", StringComparison.Ordinal) >= 0)
            {
                continue;
            }

            // Apply the optional glob filter on the relative path.
            if (!StorePaths.MatchesGlob(relativeName, matcher))
            {
                continue;
            }

            // Search each line for regex matches, tracking line numbers and building a snippet.
            string fileContent = kvp.Value;
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
                    FileName = relativeName,
                    Snippet = firstSnippet!,
                    MatchingLines = matchingLines,
                });
            }
        }

        return Task.FromResult<IReadOnlyList<FileSearchResult>>(results);
    }

    /// <inheritdoc />
    public override Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default)
    {
        // No-op: directories are implicit from file paths in the in-memory store.
        return Task.CompletedTask;
    }
}
