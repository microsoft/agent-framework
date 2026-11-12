// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Helpers shared by <see cref="LocalShellExecutor"/> and <see cref="ShellSession"/> for
/// the <c>cleanEnvironment</c> mode where the spawned shell does not inherit the parent
/// process environment — except for a small allowlist of variables that the shell needs
/// to locate itself and basic tools — and for limiting where the spawned shell
/// looks for the programs it runs.
/// </summary>
internal static class EnvironmentSanitizer
{
    /// <summary>
    /// Windows environment variable that stops <c>cmd.exe</c> (and anything else that honors
    /// <c>NeedCurrentDirectoryForExePath</c>) from searching the current directory for programs.
    /// </summary>
    public const string NoDefaultCurrentDirectoryInExePath = "NoDefaultCurrentDirectoryInExePath";

    /// <summary>
    /// Variables propagated from the host environment when <c>cleanEnvironment</c> is true.
    /// Add new entries here only — both the stateless and persistent code paths consume this list.
    /// </summary>
    public static readonly IReadOnlyList<string> PreservedVariables = new[]
    {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "SystemRoot",
        "TEMP",
        "TMP",
    };

    /// <summary>
    /// Limit where the spawned shell looks for programs named without a path, such as <c>git</c>,
    /// so the lookup never depends on the shell's working directory.
    /// </summary>
    /// <remarks>
    /// <list type="bullet">
    /// <item><description>Empty and relative entries are removed from <c>PATH</c>.</description></item>
    /// <item><description>On Windows, <c>NoDefaultCurrentDirectoryInExePath</c> is set so <c>cmd.exe</c>
    /// does not look in the current directory before <c>PATH</c>.</description></item>
    /// </list>
    /// Call this after all other changes to <paramref name="environment"/> have been applied.
    /// </remarks>
    /// <param name="environment">The environment dictionary to update in-place.</param>
    /// <exception cref="InvalidOperationException">
    /// On platforms other than Windows, <c>PATH</c> is missing or has no fully qualified directories.
    /// </exception>
    public static void RestrictExecutableSearch(IDictionary<string, string?> environment)
    {
        if (environment is null)
        {
            return;
        }

        var isWindows = RuntimeInformation.IsOSPlatform(OSPlatform.Windows);

        // Environment variable names are case-insensitive on Windows (PATH is usually spelled "Path").
        var nameComparison = isWindows ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var pathNames = new List<string>();
        foreach (var name in environment.Keys)
        {
            if (string.Equals(name, "PATH", nameComparison))
            {
                pathNames.Add(name);
            }
        }

        var hasUsablePath = false;
        foreach (var name in pathNames)
        {
            var filtered = PathValidation.RemoveRelativePathEntries(environment[name]);
            environment[name] = filtered;
            hasUsablePath |= filtered.Length > 0;
        }

        if (isWindows)
        {
            environment[NoDefaultCurrentDirectoryInExePath] = "1";
        }
        else if (!hasUsablePath)
        {
            // POSIX shells treat an empty PATH as the current directory, and bash may use a built-in
            // default that includes it when PATH is missing.
            throw new InvalidOperationException(
                "The shell's PATH has no fully qualified directories. Set LocalShellExecutorOptions.Environment[\"PATH\"] to a list of full directory paths.");
        }
    }

    /// <summary>
    /// Strip everything from <paramref name="environment"/> except the entries named by
    /// <see cref="PreservedVariables"/>. Lookup is case-insensitive so it works on both
    /// Windows (case-insensitive env vars) and POSIX (case-sensitive but typed in the
    /// expected case). Variables that aren't present in the input dictionary are skipped.
    /// </summary>
    /// <param name="environment">The environment dictionary to sanitize in-place.</param>
    public static void RemoveNonPreserved(IDictionary<string, string?> environment)
    {
        if (environment is null)
        {
            return;
        }

        var keep = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        foreach (var name in PreservedVariables)
        {
            if (environment.TryGetValue(name, out var v) && v is not null)
            {
                keep[name] = v;
            }
        }

        environment.Clear();
        foreach (var kv in keep)
        {
            environment[kv.Key] = kv.Value;
        }
    }
}
