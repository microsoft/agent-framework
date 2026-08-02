// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Branch coverage for <see cref="ShellResult.FormatForModel"/>. The output of
/// this method is what the language model sees, so regressions directly
/// affect agent behavior.
/// </summary>
public sealed class ShellResultTests
{
    [Fact]
    public void FormatForModel_Success_IncludesStdoutAndExitCode()
    {
        var r = new ShellResult("hello\n", string.Empty, 0, TimeSpan.FromMilliseconds(5));
        var s = r.FormatForModel();
        Assert.Contains("hello", s, StringComparison.Ordinal);
        Assert.Contains("exit_code: 0", s, StringComparison.Ordinal);
        Assert.DoesNotContain("stderr:", s, StringComparison.Ordinal);
        Assert.DoesNotContain("[stdout truncated]", s, StringComparison.Ordinal);
        Assert.DoesNotContain("[command timed out]", s, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatForModel_EmptyStdout_OmitsStdoutBlock()
    {
        var r = new ShellResult(string.Empty, string.Empty, 0, TimeSpan.Zero);
        var s = r.FormatForModel();
        // No stdout block, no stderr block — just the exit code line.
        Assert.Equal("exit_code: 0", s);
    }

    [Fact]
    public void FormatForModel_NonEmptyStderr_IncludesStderrLabel()
    {
        var r = new ShellResult(string.Empty, "boom\n", 1, TimeSpan.Zero);
        var s = r.FormatForModel();
        Assert.Contains("stderr: boom", s, StringComparison.Ordinal);
        Assert.Contains("exit_code: 1", s, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatForModel_Truncated_AppendsTruncatedMarker()
    {
        var r = new ShellResult("partial-output", string.Empty, 0, TimeSpan.Zero, Truncated: true);
        var s = r.FormatForModel();
        Assert.Contains("[stdout truncated]", s, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatForModel_TimedOut_AppendsTimedOutMarker()
    {
        var r = new ShellResult(string.Empty, string.Empty, 124, TimeSpan.FromSeconds(30), TimedOut: true);
        var s = r.FormatForModel();
        Assert.Contains("[command timed out]", s, StringComparison.Ordinal);
        Assert.Contains("exit_code: 124", s, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatForModel_TruncatedButEmptyStdout_DoesNotEmitMarker()
    {
        // Marker is only emitted inside the stdout block; with empty stdout
        // there's no block to attach it to.
        var r = new ShellResult(string.Empty, "err\n", 1, TimeSpan.Zero, Truncated: true);
        var s = r.FormatForModel();
        Assert.DoesNotContain("[stdout truncated]", s, StringComparison.Ordinal);
        Assert.Contains("stderr: err", s, StringComparison.Ordinal);
    }
}
