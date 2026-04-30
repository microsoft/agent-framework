// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Resolves which shell binary and which argv to launch for the current OS.
/// </summary>
/// <remarks>
/// Mirrors the Python <c>_resolve.py</c> contract:
/// <list type="bullet">
/// <item><description>Windows: prefer <c>pwsh</c>, fall back to <c>powershell.exe</c>, then <c>cmd.exe</c>.</description></item>
/// <item><description>Linux / macOS: prefer <c>/bin/bash</c>, fall back to <c>/bin/sh</c>.</description></item>
/// <item><description>Override via the constructor argument or the <c>AGENT_FRAMEWORK_SHELL</c> environment variable.</description></item>
/// </list>
/// </remarks>
internal static class ShellResolver
{
    internal const string EnvVarName = "AGENT_FRAMEWORK_SHELL";

    /// <summary>Resolve the shell binary and the per-command argv prefix.</summary>
    public static ResolvedShell Resolve(string? overrideShell = null)
    {
        var requested = overrideShell ?? Environment.GetEnvironmentVariable(EnvVarName);
        if (!string.IsNullOrWhiteSpace(requested))
        {
            return ClassifyExplicit(requested!);
        }

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            if (TryFindOnPath("pwsh", out var pwsh))
            {
                return new ResolvedShell(pwsh, ShellKind.PowerShell);
            }
            if (TryFindOnPath("powershell", out var winps))
            {
                return new ResolvedShell(winps, ShellKind.PowerShell);
            }
            return new ResolvedShell(Path.Combine(SystemRoot(), "System32", "cmd.exe"), ShellKind.Cmd);
        }

        if (File.Exists("/bin/bash"))
        {
            return new ResolvedShell("/bin/bash", ShellKind.Bash);
        }
        return new ResolvedShell("/bin/sh", ShellKind.Bash);
    }

    private static ResolvedShell ClassifyExplicit(string path)
    {
        var name = Path.GetFileNameWithoutExtension(path).ToUpperInvariant();
        return name switch
        {
            "PWSH" or "POWERSHELL" => new ResolvedShell(path, ShellKind.PowerShell),
            "CMD" => new ResolvedShell(path, ShellKind.Cmd),
            _ => new ResolvedShell(path, ShellKind.Bash),
        };
    }

    private static bool TryFindOnPath(string name, out string fullPath)
    {
        var pathEnv = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrEmpty(pathEnv))
        {
            fullPath = string.Empty;
            return false;
        }
        var exts = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? new[] { ".exe", ".cmd", ".bat", string.Empty }
            : new[] { string.Empty };
        foreach (var dir in pathEnv!.Split(Path.PathSeparator))
        {
            if (string.IsNullOrEmpty(dir))
            {
                continue;
            }
            foreach (var ext in exts)
            {
                var candidate = Path.Combine(dir, name + ext);
                if (File.Exists(candidate))
                {
                    fullPath = candidate;
                    return true;
                }
            }
        }
        fullPath = string.Empty;
        return false;
    }

    private static string SystemRoot() =>
        Environment.GetEnvironmentVariable("SystemRoot") ?? @"C:\Windows";
}

/// <summary>Identifies the dialect of the resolved shell.</summary>
internal enum ShellKind
{
    /// <summary>POSIX shell (bash, sh, zsh).</summary>
    Bash,
    /// <summary>PowerShell (pwsh or Windows PowerShell).</summary>
    PowerShell,
    /// <summary>Windows cmd.exe.</summary>
    Cmd,
}

internal readonly record struct ResolvedShell(string Binary, ShellKind Kind)
{
    public IReadOnlyList<string> StatelessArgvForCommand(string command) => this.Kind switch
    {
        ShellKind.PowerShell =>
        [
            "-NoProfile",
            "-NoLogo",
            "-NonInteractive",
            "-Command",
            command,
        ],
        ShellKind.Cmd => ["/d", "/c", command],
        _ => ["--noprofile", "--norc", "-c", command],
    };

    /// <summary>
    /// Argv for launching a long-lived shell that reads commands from stdin.
    /// </summary>
    public IReadOnlyList<string> PersistentArgv() => this.Kind switch
    {
        ShellKind.PowerShell =>
        [
            "-NoProfile",
            "-NoLogo",
            "-NonInteractive",
            "-Command",
            "-",
        ],
        ShellKind.Cmd => throw new NotSupportedException(
            "Persistent mode is not supported for cmd.exe — use pwsh, powershell, or a POSIX shell."),
        _ => ["--noprofile", "--norc"],
    };
}
