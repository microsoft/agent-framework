// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Extensions.FileSystemGlobbing;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal helper for normalizing and validating relative store paths and matching glob patterns.
/// Shared across <see cref="AgentFileStore"/> implementations and <see cref="FileMemoryProvider"/>.
/// </summary>
internal static class StorePaths
{
    /// <summary>
    /// Normalizes a relative path by replacing backslashes with forward slashes, trimming leading
    /// and trailing separators, and collapsing consecutive separators. Also validates that the path
    /// does not contain rooted paths, drive roots, or <c>.</c>/<c>..</c> traversal segments.
    /// </summary>
    /// <param name="path">The relative path to normalize.</param>
    /// <param name="isDirectory">
    /// When <see langword="true"/>, the path represents a directory and an empty result (meaning root) is allowed.
    /// When <see langword="false"/> (default), the path represents a file and an empty result is rejected.
    /// </param>
    /// <returns>The normalized forward-slash path.</returns>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="path"/> is rooted, starts with a drive letter, contains
    /// <c>.</c> or <c>..</c> segments, or is empty when <paramref name="isDirectory"/> is <see langword="false"/>.
    /// </exception>
    internal static string NormalizeRelativePath(string path, bool isDirectory = false)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            if (!isDirectory)
            {
                throw new ArgumentException("A file path must not be empty or whitespace-only.", nameof(path));
            }

            return string.Empty;
        }

        string normalized = path.Replace('\\', '/').Trim('/');

        if (Path.IsPathRooted(path) ||
            path.StartsWith("/", StringComparison.Ordinal) ||
            path.StartsWith("\\", StringComparison.Ordinal) ||
            (normalized.Length >= 2 && char.IsLetter(normalized[0]) && normalized[1] == ':'))
        {
            throw new ArgumentException(
                $"Invalid path: '{path}'. Paths must be relative and must not start with '/', '\\', or a drive root.",
                nameof(path));
        }

        // Split, validate segments, and filter out empty segments to collapse consecutive separators.
        string[] segments = normalized.Split('/');
        var cleanSegments = new List<string>(segments.Length);
        foreach (string segment in segments)
        {
            if (segment.Length == 0)
            {
                continue;
            }

            if (segment.Equals(".", StringComparison.Ordinal) || segment.Equals("..", StringComparison.Ordinal))
            {
                throw new ArgumentException(
                    $"Invalid path: '{path}'. Paths must not contain '.' or '..' segments.",
                    nameof(path));
            }

            cleanSegments.Add(segment);
        }

        string result = string.Join("/", cleanSegments);

        if (!isDirectory && result.Length == 0)
        {
            throw new ArgumentException("A file path must not be empty.", nameof(path));
        }

        return result;
    }

    /// <summary>
    /// Creates a <see cref="Matcher"/> for the specified glob pattern. Use the returned instance
    /// to test multiple file names without allocating a new matcher for each one.
    /// </summary>
    /// <param name="filePattern">
    /// The glob pattern to match against (e.g., <c>"*.md"</c>, <c>"research*"</c>).
    /// </param>
    /// <returns>A <see cref="Matcher"/> configured with the specified pattern.</returns>
    internal static Matcher CreateGlobMatcher(string filePattern)
    {
        var matcher = new Matcher(StringComparison.OrdinalIgnoreCase);
        matcher.AddInclude(filePattern);
        return matcher;
    }

    /// <summary>
    /// Determines whether a file name matches a pre-built glob <see cref="Matcher"/>.
    /// </summary>
    /// <param name="fileName">The file name to test (not a full path — just the name).</param>
    /// <param name="matcher">
    /// A pre-built <see cref="Matcher"/> to test against.
    /// When <see langword="null"/>, this method returns <see langword="true"/> for any file name.
    /// </param>
    /// <returns><see langword="true"/> if the file name matches the pattern or if the matcher is <see langword="null"/>; otherwise, <see langword="false"/>.</returns>
    internal static bool MatchesGlob(string fileName, Matcher? matcher)
    {
        if (matcher is null)
        {
            return true;
        }

        PatternMatchingResult result = matcher.Match(fileName);
        return result.HasMatches;
    }
}
