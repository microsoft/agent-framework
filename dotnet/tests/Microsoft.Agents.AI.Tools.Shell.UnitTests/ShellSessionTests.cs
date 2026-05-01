// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Direct coverage for <see cref="ShellSession.TruncateHeadTail"/> (internal,
/// reachable via InternalsVisibleTo). The function is on the hot path for
/// every shell command — both LocalShellTool and DockerShellTool feed
/// captured stdout/stderr through it before returning.
/// </summary>
public sealed class ShellSessionTests
{
    [Fact]
    public void TruncateHeadTail_UnderCap_ReturnsInputUnchanged()
    {
        const string Input = "short";
        var (text, truncated) = ShellSession.TruncateHeadTail(Input, cap: 1024);
        Assert.Equal(Input, text);
        Assert.False(truncated);
    }

    [Fact]
    public void TruncateHeadTail_ExactlyAtCap_ReturnsInputUnchanged()
    {
        var input = new string('x', 100);
        var (text, truncated) = ShellSession.TruncateHeadTail(input, cap: 100);
        Assert.Equal(input, text);
        Assert.False(truncated);
    }

    [Fact]
    public void TruncateHeadTail_OverCap_TruncatesAndIncludesMarker()
    {
        var input = "HEAD" + new string('x', 1000) + "TAIL";
        var (text, truncated) = ShellSession.TruncateHeadTail(input, cap: 20);
        Assert.True(truncated);
        Assert.Contains("[... truncated", text, StringComparison.Ordinal);
        Assert.Contains("HEAD", text, StringComparison.Ordinal);
        Assert.Contains("TAIL", text, StringComparison.Ordinal);
        // Truncated output is roughly cap + marker chars; confirm it's much
        // smaller than the input.
        Assert.True(text.Length < input.Length);
    }

    [Fact]
    public void TruncateHeadTail_EmptyString_ReturnsEmpty()
    {
        var (text, truncated) = ShellSession.TruncateHeadTail(string.Empty, cap: 10);
        Assert.Equal(string.Empty, text);
        Assert.False(truncated);
    }
}
