// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Configuration for <see cref="LocalShellExecutor"/>. New knobs will be
/// added as properties here so the constructor surface stays binary-stable.
/// </summary>
public sealed class LocalShellExecutorOptions
{
    /// <summary>
    /// Execution mode. Defaults to <see cref="ShellMode.Persistent"/>.
    /// <para>
    /// In <see cref="ShellMode.Persistent"/> the resulting executor instance is owned by
    /// a single conversation / agent session; do not share it across users or concurrent
    /// sessions. See <see cref="LocalShellExecutor"/> remarks.
    /// </para>
    /// </summary>
    public ShellMode Mode { get; set; } = ShellMode.Persistent;

    /// <summary>
    /// Override path to the shell binary. Falls back to the
    /// <c>AGENT_FRAMEWORK_SHELL</c> environment variable, then OS defaults.
    /// Mutually exclusive with <see cref="ShellArgv"/>.
    /// </summary>
    /// <remarks>
    /// The value (and the <c>AGENT_FRAMEWORK_SHELL</c> environment variable) must be a fully
    /// qualified path, such as <c>/bin/bash</c> or <c>C:\Program Files\PowerShell\7\pwsh.exe</c>.
    /// On Windows it must also include a file extension, such as <c>.exe</c>. Bare names such as
    /// <c>pwsh</c> are rejected. When no override is set, the OS default shell is located by
    /// searching only the fully qualified directories in <c>PATH</c>.
    /// </remarks>
    public string? Shell { get; set; }

    /// <summary>
    /// Override argv for the shell launch. The first element is the binary;
    /// subsequent elements are passed as a launch-time prefix. Mutually
    /// exclusive with <see cref="Shell"/>.
    /// </summary>
    /// <remarks>
    /// The first element must be a fully qualified path, and on Windows must include a
    /// file extension, such as <c>.exe</c>.
    /// </remarks>
    public IReadOnlyList<string>? ShellArgv { get; set; }

    /// <summary>
    /// Working directory for the spawned shell. Defaults to the current
    /// process directory. Required when <see cref="ConfineWorkingDirectory"/>
    /// is <see langword="true"/>.
    /// </summary>
    public string? WorkingDirectory { get; set; }

    /// <summary>
    /// When <see langword="true"/> (the default), every command in
    /// persistent mode is prefixed with a <c>cd</c> back into
    /// <see cref="WorkingDirectory"/> so a wandering <c>cd</c> in one call
    /// doesn't leak to the next.
    /// </summary>
    public bool ConfineWorkingDirectory { get; set; } = true;

    /// <summary>
    /// Extra environment variables. Pass a <see langword="null"/> value to
    /// remove an inherited variable.
    /// </summary>
    /// <remarks>
    /// The shell always looks for programs only in the fully qualified directories of
    /// <c>PATH</c>: empty and relative entries (such as <c>.</c>) are removed from the
    /// <c>PATH</c> passed to the shell, including a <c>PATH</c> supplied here. On Windows,
    /// <c>NoDefaultCurrentDirectoryInExePath</c> is also set, so <c>cmd.exe</c> does not run
    /// programs from the working directory unless they are named with a path, such as
    /// <c>.\tool.exe</c>.
    /// </remarks>
    public IReadOnlyDictionary<string, string?>? Environment { get; set; }

    /// <summary>
    /// When <see langword="true"/>, the spawned shell does not inherit the
    /// parent process environment.
    /// </summary>
    public bool CleanEnvironment { get; set; }

    /// <summary>
    /// Optional <see cref="ShellPolicy"/>. When <see langword="null"/>,
    /// a default (empty) policy is used that allows any non-empty command.
    /// Supply a <see cref="ShellPolicy"/> with explicit deny/allow
    /// patterns if you want pre-execution rejection of specific command
    /// shapes; note that pattern matching is a UX pre-filter, not a
    /// security control (see <see cref="ShellPolicy"/> remarks).
    /// </summary>
    public ShellPolicy? Policy { get; set; }

    /// <summary>
    /// Per-command timeout. <see langword="null"/> (the default) disables
    /// timeouts. See <see cref="LocalShellExecutor.DefaultTimeout"/> for the
    /// recommended value.
    /// </summary>
    public TimeSpan? Timeout { get; set; }

    /// <summary>Per-stream cap before head+tail truncation. Defaults to 64 KiB.</summary>
    public int MaxOutputBytes { get; set; } = 64 * 1024;

    /// <summary>
    /// Set to <see langword="true"/> to allow
    /// <see cref="LocalShellExecutor.AsAIFunction"/> to produce an
    /// AIFunction without an <c>ApprovalRequiredAIFunction</c> wrapper.
    /// </summary>
    public bool AcknowledgeUnsafe { get; set; }
}
