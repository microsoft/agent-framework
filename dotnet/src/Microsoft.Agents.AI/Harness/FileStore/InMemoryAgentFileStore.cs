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
    public override Task WriteFileAsync(string path, string content, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        this._files[path] = content;
        return Task.CompletedTask;
    }

    /// <inheritdoc />
    public override Task<string?> ReadFileAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        this._files.TryGetValue(path, out string? content);
        return Task.FromResult(content);
    }

    /// <inheritdoc />
    public override Task<bool> DeleteFileAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        return Task.FromResult(this._files.TryRemove(path, out _));
    }

    /// <inheritdoc />
    public override Task<IReadOnlyList<string>> ListFilesAsync(string directory, CancellationToken cancellationToken = default)
    {
        string prefix = StorePaths.NormalizeRelativePath(directory, isDirectory: true);
        if (prefix.Length > 0 && !prefix.EndsWith("/", StringComparison.Ordinal))
        {
            prefix += "/";
        }

        var files = this._files.Keys
            .Where(k => k.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            .Select(k => k.Substring(prefix.Length))
            .Where(k => k.IndexOf("/", StringComparison.Ordinal) < 0)
            .ToList();

        return Task.FromResult<IReadOnlyList<string>>(files);
    }

    /// <inheritdoc />
    public override Task<bool> FileExistsAsync(string path, CancellationToken cancellationToken = default)
    {
        path = StorePaths.NormalizeRelativePath(path);
        return Task.FromResult(this._files.ContainsKey(path));
    }

    /// <inheritdoc />
    public override Task<IReadOnlyList<FileSearchResult>> SearchFilesAsync(string directory, string regexPattern, string? filePattern = null, CancellationToken cancellationToken = default)
    {
        // Normalize the directory prefix for path matching.
        string prefix = StorePaths.NormalizeRelativePath(directory, isDirectory: true);
        if (prefix.Length > 0 && !prefix.EndsWith("/", StringComparison.Ordinal))
        {
            prefix += "/";
        }

        // Compile the regex with a timeout to guard against catastrophic backtracking (ReDoS).
        var regex = new Regex(regexPattern, RegexOptions.IgnoreCase, TimeSpan.FromSeconds(5));
        Matcher? matcher = filePattern is not null ? StorePaths.CreateGlobMatcher(filePattern) : null;
        var results = new List<FileSearchResult>();

        foreach (var kvp in this._files)
        {
            // Only consider files within the target directory (by path prefix).
            if (!kvp.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            // Exclude files in subdirectories (direct children only).
            string relativeName = kvp.Key.Substring(prefix.Length);
            if (relativeName.IndexOf("/", StringComparison.Ordinal) >= 0)
            {
                continue;
            }

            // Apply the optional glob filter on the file name.
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
