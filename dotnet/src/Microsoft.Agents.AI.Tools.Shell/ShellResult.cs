// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// The outcome of a single shell command invocation.
/// </summary>
/// <param name="Stdout">Captured standard output, possibly truncated.</param>
/// <param name="Stderr">Captured standard error, possibly truncated.</param>
/// <param name="ExitCode">The exit status reported by the shell or subprocess. <c>-1</c> if the process never exited cleanly.</param>
/// <param name="Duration">How long the command took to execute end-to-end.</param>
/// <param name="Truncated"><see langword="true"/> when stdout or stderr was truncated.</param>
/// <param name="TimedOut"><see langword="true"/> when the command was killed because it exceeded the configured timeout.</param>
public sealed record ShellResult(
    string Stdout,
    string Stderr,
    int ExitCode,
    TimeSpan Duration,
    bool Truncated = false,
    bool TimedOut = false)
{
    /// <summary>
    /// Format the result as a single text block suitable for return to a language model.
    /// </summary>
    /// <returns>A multi-line string combining stdout, stderr, status flags, and the exit code.</returns>
    public string FormatForModel()
    {
        var sb = new StringBuilder();
        if (!string.IsNullOrEmpty(this.Stdout))
        {
            _ = sb.Append(this.Stdout);
            if (this.Truncated)
            {
                _ = sb.AppendLine().Append("[stdout truncated]");
            }
            _ = sb.AppendLine();
        }
        if (!string.IsNullOrEmpty(this.Stderr))
        {
            _ = sb.Append("stderr: ").Append(this.Stderr).AppendLine();
        }
        if (this.TimedOut)
        {
            _ = sb.AppendLine("[command timed out]");
        }
        _ = sb.Append("exit_code: ").Append(this.ExitCode);
        return sb.ToString();
    }
}
