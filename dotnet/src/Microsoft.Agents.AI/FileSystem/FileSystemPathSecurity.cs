// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Runtime.InteropServices;

namespace Microsoft.Agents.AI;

internal static class FileSystemPathSecurity
{
    internal static bool IsPathWithinDirectory(string pathToCheck, string trustedBasePath)
    {
        string fullPath = EnsureTrailingSeparator(Path.GetFullPath(pathToCheck));
        string fullBase = EnsureTrailingSeparator(Path.GetFullPath(trustedBasePath));
        return fullPath.StartsWith(fullBase, GetPathComparison());
    }

    internal static bool HasSymlinkInPath(string pathToCheck, string trustedBasePath)
    {
        string fullPath = Path.GetFullPath(pathToCheck);
        string fullBase = EnsureTrailingSeparator(Path.GetFullPath(trustedBasePath));
        if (!fullPath.StartsWith(fullBase, GetPathComparison()))
        {
            return false;
        }

        string relativePath = fullPath.Substring(fullBase.Length);
        string[] segments = relativePath.Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar], StringSplitOptions.RemoveEmptyEntries);
        string currentPath = fullBase.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        foreach (string segment in segments)
        {
            currentPath = Path.Combine(currentPath, segment);
            if (!File.Exists(currentPath) && !Directory.Exists(currentPath))
            {
                continue;
            }

            if ((File.GetAttributes(currentPath) & FileAttributes.ReparsePoint) != 0)
            {
                return true;
            }
        }

        return false;
    }

    private static string EnsureTrailingSeparator(string path)
    {
        return path.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal) ||
            path.EndsWith(Path.AltDirectorySeparatorChar.ToString(), StringComparison.Ordinal) ? path : path + Path.DirectorySeparatorChar;
    }

    private static StringComparison GetPathComparison() => RuntimeInformation.IsOSPlatform(OSPlatform.Windows) ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
}
