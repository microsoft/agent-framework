// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Resolves which shell binary and which argv to launch for the current OS.
/// </summary>
/// <remarks>
/// Resolution order:
/// <list type="bullet">
/// <item><description>Windows: prefer <c>pwsh.exe</c>, fall back to <c>powershell.exe</c>, then <c>%SystemRoot%\System32\cmd.exe</c>.
/// Only fully qualified <c>PATH</c> entries are searched.</description></item>
/// <item><description>Linux / macOS: prefer <c>/bin/bash</c>, fall back to <c>/bin/sh</c>.</description></item>
/// <item><description>Override via the constructor argument or the <c>AGENT_FRAMEWORK_SHELL</c> environment variable.
/// An override must be a fully qualified path, and on Windows must include a file extension.</description></item>
/// </list>
/// </remarks>
internal static class ShellResolver
{
    /// <summary>
    /// The environment variable consulted by <see cref="Resolve"/> to override
    /// the default shell selection (e.g. <c>AGENT_FRAMEWORK_SHELL=/usr/bin/bash</c>).
    /// </summary>
    public const string EnvVarName = "AGENT_FRAMEWORK_SHELL";

    /// <summary>Resolve the shell binary and the per-command argv prefix.</summary>
    /// <param name="overrideShell">
    /// Optional fully qualified path to the shell binary. When <see langword="null"/> or whitespace, the
    /// <c>AGENT_FRAMEWORK_SHELL</c> environment variable is consulted, then OS defaults.
    /// </param>
    /// <param name="paramName">The name of the parameter that supplied <paramref name="overrideShell"/>, used in error messages.</param>
    /// <exception cref="ArgumentException">
    /// The override is not a fully qualified path, or on Windows has no file extension.
    /// </exception>
    public static ResolvedShell Resolve(string? overrideShell = null, string paramName = "overrideShell")
    {
        if (!string.IsNullOrWhiteSpace(overrideShell))
        {
            return ClassifyExplicit(overrideShell!, paramName, "shell");
        }

        var fromEnv = Environment.GetEnvironmentVariable(EnvVarName);
        if (!string.IsNullOrWhiteSpace(fromEnv))
        {
            return ClassifyExplicit(fromEnv!, EnvVarName, EnvVarName);
        }

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            var pathEnv = Environment.GetEnvironmentVariable("PATH");
            if (PathValidation.TryFindOnPath(pathEnv, "pwsh.exe", out var pwsh))
            {
                return new ResolvedShell(pwsh, ShellKind.PowerShell);
            }
            if (PathValidation.TryFindOnPath(pathEnv, "powershell.exe", out var winps))
            {
                return new ResolvedShell(winps, ShellKind.PowerShell);
            }
            return new ResolvedShell(Path.Combine(WindowsSystemRoot(), "System32", "cmd.exe"), ShellKind.Cmd);
        }

        if (File.Exists("/bin/bash"))
        {
            return new ResolvedShell("/bin/bash", ShellKind.Bash);
        }
        return new ResolvedShell("/bin/sh", ShellKind.Sh);
    }

    /// <summary>
    /// Resolve from an explicit argv list. The first element is treated as
    /// the binary; the rest are passed as a launch-time prefix preceding
    /// the standard <c>-c</c> / <c>-Command</c> / persistent suffix.
    /// </summary>
    /// <param name="shellArgv">The argv list. The first element must be a fully qualified path, and on Windows must include a file extension.</param>
    /// <param name="paramName">The name of the parameter that supplied <paramref name="shellArgv"/>, used in error messages.</param>
    /// <exception cref="ArgumentException">
    /// <paramref name="shellArgv"/> is empty, or its first element is not a fully qualified path, or on Windows has no file extension.
    /// </exception>
    public static ResolvedShell ResolveArgv(IReadOnlyList<string> shellArgv, string paramName = "shellArgv")
    {
        if (shellArgv is null)
        {
            throw new ArgumentNullException(paramName);
        }
        if (shellArgv.Count == 0)
        {
            throw new ArgumentException("shellArgv must contain at least the binary path.", paramName);
        }
        var binary = shellArgv[0];
        PathValidation.ValidateFullyQualifiedExecutablePath(binary, paramName, "shell");
        var kind = ClassifyKind(binary);
        var extra = shellArgv.Count > 1 ? new string[shellArgv.Count - 1] : Array.Empty<string>();
        for (var i = 1; i < shellArgv.Count; i++)
        {
            extra[i - 1] = shellArgv[i];
        }
        return new ResolvedShell(binary, kind, ExtraArgv: extra);
    }

    private static ResolvedShell ClassifyExplicit(string path, string paramName, string fileDescription)
    {
        PathValidation.ValidateFullyQualifiedExecutablePath(path, paramName, fileDescription);
        return new(path, ClassifyKind(path));
    }

    private static ShellKind ClassifyKind(string path)
    {
        var name = Path.GetFileNameWithoutExtension(path).ToUpperInvariant();
        return name switch
        {
            "PWSH" or "POWERSHELL" => ShellKind.PowerShell,
            "CMD" => ShellKind.Cmd,
            "BASH" => ShellKind.Bash,
            // All other POSIX shells (sh, zsh, dash, ash, ksh, busybox, ...)
            // are launched as plain sh so we don't pass bash-only flags like
            // --noprofile / --norc, which zsh and dash reject.
            _ => ShellKind.Sh,
        };
    }

    private static string WindowsSystemRoot()
    {
        var systemRoot = Environment.GetEnvironmentVariable("SystemRoot");
        return PathValidation.IsFullyQualifiedPath(systemRoot) ? systemRoot : @"C:\Windows";
    }
}

/// <summary>Identifies the dialect of the resolved shell.</summary>
internal enum ShellKind
{
    /// <summary>POSIX bash; supports <c>--noprofile</c> / <c>--norc</c>.</summary>
    Bash,
    /// <summary>PowerShell (pwsh or Windows PowerShell).</summary>
    PowerShell,
    /// <summary>Windows cmd.exe.</summary>
    Cmd,
    /// <summary>Generic POSIX shell (sh, zsh, dash, ash, ksh, busybox) — bash-only flags are not passed.</summary>
    Sh,
}

internal readonly record struct ResolvedShell(string Binary, ShellKind Kind, IReadOnlyList<string>? ExtraArgv = null)
{
    public IReadOnlyList<string> StatelessArgvForCommand(string command)
    {
        var extra = this.ExtraArgv ?? Array.Empty<string>();
        var suffix = this.Kind switch
        {
            ShellKind.PowerShell => new[]
            {
                "-NoProfile",
                "-NoLogo",
                "-NonInteractive",
                "-Command",
                command,
            },
            ShellKind.Cmd => new[] { "/d", "/c", command },
            ShellKind.Sh => new[] { "-c", command },
            _ => new[] { "--noprofile", "--norc", "-c", command },
        };
        if (extra.Count == 0)
        {
            return suffix;
        }
        var combined = new string[extra.Count + suffix.Length];
        for (var i = 0; i < extra.Count; i++) { combined[i] = extra[i]; }
        for (var i = 0; i < suffix.Length; i++) { combined[extra.Count + i] = suffix[i]; }
        return combined;
    }

    /// <summary>
    /// Argv for launching a long-lived shell that reads commands from stdin.
    /// </summary>
    public IReadOnlyList<string> PersistentArgv()
    {
        var extra = this.ExtraArgv ?? Array.Empty<string>();
        var suffix = this.Kind switch
        {
            ShellKind.PowerShell => new[]
            {
                "-NoProfile",
                "-NoLogo",
                "-NonInteractive",
                "-Command",
                "-",
            },
            ShellKind.Cmd => throw new NotSupportedException(
                "Persistent mode is not supported for cmd.exe — use pwsh, powershell, or a POSIX shell."),
            ShellKind.Sh => Array.Empty<string>(),
            _ => new[] { "--noprofile", "--norc" },
        };
        if (extra.Count == 0)
        {
            return suffix;
        }
        var combined = new string[extra.Count + suffix.Length];
        for (var i = 0; i < extra.Count; i++) { combined[i] = extra[i]; }
        for (var i = 0; i < suffix.Length; i++) { combined[extra.Count + i] = suffix[i]; }
        return combined;
    }
}
