// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// A point-in-time snapshot of the shell environment the agent is using.
/// </summary>
/// <param name="Family">Shell family (PowerShell vs POSIX).</param>
/// <param name="OSDescription"><see cref="RuntimeInformation.OSDescription"/>.</param>
/// <param name="ShellVersion">Reported shell version, or <see langword="null"/> if probing failed.</param>
/// <param name="WorkingDirectory">CWD at probe time, or empty if probing failed.</param>
/// <param name="ToolVersions">Map of probed CLI tool name to reported version (or <see langword="null"/> when not installed).</param>
public sealed record ShellEnvironmentSnapshot(
    ShellFamily Family,
    string OSDescription,
    string? ShellVersion,
    string WorkingDirectory,
    IReadOnlyDictionary<string, string?> ToolVersions);
