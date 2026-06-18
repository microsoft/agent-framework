// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Configuration options for <see cref="LocalCodeActProvider"/> and <see cref="LocalExecuteCodeFunction"/>.
/// </summary>
public sealed class LocalCodeActProviderOptions
{
    /// <summary>Gets or sets the resource limits applied to subprocess execution and capture.</summary>
    public ProcessExecutionLimits? ExecutionLimits { get; set; }

    /// <summary>
    /// Gets or sets the initial set of host tools available to generated code via <c>await call_tool(...)</c>.
    /// </summary>
    public IEnumerable<AIFunction>? Tools { get; set; }

    /// <summary>
    /// Gets or sets the initial set of file mounts exposed to generated code.
    /// </summary>
    public IEnumerable<FileMount>? FileMounts { get; set; }

    /// <summary>
    /// Gets or sets environment variables passed to the subprocess.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the subprocess inherits the parent process environment
    /// (the default <see cref="System.Diagnostics.ProcessStartInfo"/> behavior). To run with
    /// a restricted environment, supply a dictionary containing only the variables the
    /// subprocess should see — pass an empty dictionary for a fully scrubbed environment.
    /// On Windows, a small set of system variables (SYSTEMROOT, SYSTEMDRIVE, COMSPEC,
    /// PATHEXT, TEMP, TMP) is back-filled from the parent environment when not already
    /// present so Python can locate its standard library.
    /// </remarks>
    public IReadOnlyDictionary<string, string>? Environment { get; set; }

    /// <summary>
    /// Gets or sets the working directory used for the subprocess. When <see langword="null"/>
    /// the current working directory of the host process is used.
    /// </summary>
    public string? WorkingDirectory { get; set; }

    /// <summary>
    /// Gets or sets the optional override path to the Python runner script. When <see langword="null"/>
    /// the embedded <c>runner.py</c> is extracted to a temporary directory and used.
    /// </summary>
    public string? RunnerScriptPath { get; set; }

    /// <summary>
    /// Gets or sets the optional override path to the Python validator script. When <see langword="null"/>
    /// the embedded <c>validator.py</c> is extracted to a temporary directory and used.
    /// </summary>
    public string? ValidatorScriptPath { get; set; }

    /// <summary>
    /// Gets or sets whether AST allow-list validation is disabled. Defaults to <see langword="false"/>.
    /// </summary>
    /// <remarks>
    /// Disabling validation removes a critical defense-in-depth control. Only disable when the
    /// generated code is trusted or when running inside a strong external sandbox.
    /// </remarks>
    public bool ValidationDisabled { get; set; }

    /// <summary>
    /// Gets or sets the set of imports allowed by the validator. When <see langword="null"/>
    /// the validator's built-in defaults are used. Setting a value replaces the defaults.
    /// </summary>
    public IEnumerable<string>? AllowedImports { get; set; }

    /// <summary>
    /// Gets or sets the set of imports blocked by the validator. When <see langword="null"/>
    /// the validator's built-in defaults are used. Setting a value replaces the defaults.
    /// </summary>
    public IEnumerable<string>? BlockedImports { get; set; }

    /// <summary>
    /// Gets or sets the set of builtins allowed by the validator. When <see langword="null"/>
    /// the validator's built-in defaults are used. Setting a value replaces the defaults.
    /// </summary>
    public IEnumerable<string>? AllowedBuiltins { get; set; }

    /// <summary>
    /// Gets or sets the set of builtins blocked by the validator. When <see langword="null"/>
    /// the validator's built-in defaults are used. Setting a value replaces the defaults.
    /// </summary>
    public IEnumerable<string>? BlockedBuiltins { get; set; }
}
