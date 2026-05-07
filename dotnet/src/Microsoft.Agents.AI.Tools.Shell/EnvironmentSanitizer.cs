// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Helpers shared by <see cref="LocalShellExecutor"/> and <see cref="ShellSession"/> for
/// the <c>cleanEnvironment</c> mode where the spawned shell does not inherit the parent
/// process environment — except for a small allowlist of variables that the shell needs
/// to locate itself and basic tools.
/// </summary>
internal static class EnvironmentSanitizer
{
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
