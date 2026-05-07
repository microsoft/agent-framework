// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Specifies how a shell executor dispatches commands to the underlying shell.
/// </summary>
public enum ShellMode
{
    /// <summary>
    /// Each command runs in a fresh shell subprocess. State (working directory,
    /// environment variables) is reset between calls.
    /// </summary>
    Stateless,

    /// <summary>
    /// A single long-lived shell subprocess is reused across calls so
    /// <c>cd</c> and exported / <c>$env:</c> variables persist between
    /// invocations. Commands are executed via a sentinel protocol that
    /// brackets stdout to determine completion. This is the recommended
    /// default for coding agents because it eliminates the "agent runs cd
    /// and then runs the wrong path" failure class.
    /// </summary>
    Persistent,
}
