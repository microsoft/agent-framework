// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Configuration knobs for <see cref="ShellEnvironmentProvider"/>.
/// </summary>
public sealed class ShellEnvironmentProviderOptions
{
    /// <summary>
    /// CLI tools whose <c>--version</c> output is probed and surfaced in
    /// the agent context. Defaults to a small, common set.
    /// </summary>
    public IReadOnlyList<string> ProbeTools { get; init; } =
        ["git", "dotnet", "node", "python", "docker"];

    /// <summary>
    /// Optional override for the auto-detected shell family. When
    /// <see langword="null"/>, the family is inferred from
    /// <see cref="RuntimeInformation"/> (Windows -> PowerShell, otherwise
    /// POSIX). Set this when running against a non-default shell (e.g.,
    /// bash on Windows via WSL, or pwsh on Linux).
    /// </summary>
    public ShellFamily? OverrideFamily { get; init; }

    /// <summary>
    /// Per-probe execution timeout. Failed or timed-out probes are
    /// recorded as missing rather than thrown to the agent.
    /// </summary>
    public TimeSpan ProbeTimeout { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// Optional formatter for the instructions block. When
    /// <see langword="null"/>, a built-in formatter is used.
    /// </summary>
    public Func<ShellEnvironmentSnapshot, string>? InstructionsFormatter { get; init; }
}
