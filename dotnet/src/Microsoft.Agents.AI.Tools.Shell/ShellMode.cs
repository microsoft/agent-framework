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
    /// <para>
    /// <b>Single-session ownership.</b> Because the underlying shell carries
    /// mutable state (working directory, exported variables, function
    /// definitions, shell history) that is intentionally visible to every
    /// command run through it, a persistent-mode executor instance is meant
    /// to be owned by exactly one conversation / agent session. Sharing one
    /// instance across users, tenants, or concurrent conversations leaks
    /// state between them and serializes their commands behind a single
    /// stdin/stdout pipe. If you need multiple sessions, create one
    /// executor per session (and dispose it when the session ends), or use
    /// <see cref="Stateless"/>.
    /// </para>
    /// </summary>
    Persistent,
}
