// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// Raw output from shell executor.
/// </summary>
public sealed class ShellExecutorOutput
{
    /// <summary>
    /// Gets or sets the command that was executed.
    /// </summary>
    public string? Command { get; set; }

    /// <summary>
    /// Gets or sets the standard output from the command.
    /// </summary>
    public string? StandardOutput { get; set; }

    /// <summary>
    /// Gets or sets the standard error from the command.
    /// </summary>
    public string? StandardError { get; set; }

    /// <summary>
    /// Gets or sets the exit code. Null if the command timed out or failed to start.
    /// </summary>
    public int? ExitCode { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the command execution timed out.
    /// </summary>
    public bool IsTimedOut { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the output was truncated due to MaxOutputLength.
    /// </summary>
    public bool IsTruncated { get; set; }

    /// <summary>
    /// Gets or sets an error message if the command failed to start.
    /// </summary>
    public string? Error { get; set; }
}
