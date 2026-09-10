// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Security;

namespace Microsoft.Agents.AI;

/// <summary>
/// Validates paths used by file-backed skills.
/// </summary>
internal static class AgentFileSkillPathValidator
{
    /// <summary>
    /// Revalidates a discovered file against its trusted path scope immediately before use.
    /// </summary>
    internal static string ValidateForUse(string fullPath, AgentFileSkillPathScope scope, string fileKind, string fileName)
    {
        string resolvedFilePath = Path.GetFullPath(fullPath);

        if (!resolvedFilePath.StartsWith(scope.SkillDirectoryPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"{fileKind} file '{fileName}' references a path outside the skill directory.");
        }

        if (!File.Exists(resolvedFilePath))
        {
            throw new FileNotFoundException($"{fileKind} file '{fileName}' was not found in the skill directory.", resolvedFilePath);
        }

        // Scan from the configured discovery root rather than from the skill directory, so that a
        // skill directory - or any directory between it and the root - that was replaced with a
        // link after discovery is rejected as well.
        if (HasLinkOrReparsePointInPath(resolvedFilePath, scope.TrustedRootPrefix))
        {
            throw new InvalidOperationException(
                $"{fileKind} file '{fileName}' has a symbolic link or reparse point in its path; links and reparse points are not allowed.");
        }

        return resolvedFilePath;
    }

    /// <summary>
    /// Checks whether any segment in the path below the trusted base is a link,
    /// reparse point, or cannot be inspected.
    /// </summary>
    internal static bool HasLinkOrReparsePointInPath(string pathToCheck, string trustedBasePath)
    {
        string relativePath = pathToCheck.Substring(trustedBasePath.Length);
        string[] segments = relativePath.Split(
            [Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar],
            StringSplitOptions.RemoveEmptyEntries);

        string currentPath = trustedBasePath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        foreach (string segment in segments)
        {
            currentPath = Path.Combine(currentPath, segment);

            if (IsLinkOrReparsePointOrInaccessible(currentPath))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Checks whether a path is a link, reparse point, or cannot be safely inspected.
    /// </summary>
    internal static bool IsLinkOrReparsePointOrInaccessible(string path)
    {
        try
        {
            return (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;
        }
        catch (Exception ex) when (IsFileSystemInspectionFailure(ex))
        {
            return true;
        }
    }

    /// <summary>
    /// Checks whether an exception indicates that a filesystem path could not be inspected.
    /// </summary>
    internal static bool IsFileSystemInspectionFailure(Exception exception)
    {
        return exception is IOException or UnauthorizedAccessException or SecurityException;
    }
}
