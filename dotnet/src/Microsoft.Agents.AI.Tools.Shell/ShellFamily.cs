// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Identifies the shell family the agent is talking to.
/// </summary>
public enum ShellFamily
{
    /// <summary>POSIX-style shell (bash, sh, zsh).</summary>
    Posix,

    /// <summary>PowerShell (pwsh or Windows PowerShell).</summary>
    PowerShell,
}
