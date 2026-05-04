// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Coverage for <see cref="HeadTailBuffer"/>, the bounded stdout/stderr accumulator
/// shared by <see cref="LocalShellTool"/> and <see cref="DockerShellTool"/>.
/// </summary>
public sealed class HeadTailBufferTests
{
    [Fact]
    public void Append_BelowCap_RoundTripsExactInput()
    {
        var buf = new HeadTailBuffer(cap: 1024);
        buf.AppendLine("hello");
        buf.AppendLine("world");

        var (text, truncated) = buf.ToFinalString();

        Assert.False(truncated);
        Assert.Equal("hello\nworld\n", text);
    }

    [Fact]
    public void Append_ManyLines_StaysBoundedAndRetainsHeadAndTail()
    {
        // Push roughly 10 MiB through a 4 KiB cap.
        var buf = new HeadTailBuffer(cap: 4096);
        for (var i = 0; i < 100_000; i++)
        {
            buf.AppendLine($"line {i:D6}");
        }

        var (text, truncated) = buf.ToFinalString();

        Assert.True(truncated);
        // Result must respect the cap (allow some overhead for the marker line).
        Assert.True(text.Length <= 4096 + 128, $"Result was {text.Length} chars, expected <= ~{4096 + 128}");
        Assert.Contains("line 000000", text, System.StringComparison.Ordinal);
        Assert.Contains("[... truncated", text, System.StringComparison.Ordinal);
        Assert.Contains("line 099999", text, System.StringComparison.Ordinal);
    }

    [Fact]
    public void Append_HugeSingleLine_DoesNotAccumulateUnbounded()
    {
        // Worst-case: a single line that is much larger than the cap — the
        // buffer must not grow without bound while we're still streaming.
        var buf = new HeadTailBuffer(cap: 1024);
        var chunk = new string('x', 10_000);
        for (var i = 0; i < 100; i++)
        {
            buf.AppendLine(chunk);
        }

        var (text, truncated) = buf.ToFinalString();

        Assert.True(truncated);
        // The exact upper bound depends on marker formatting, but it must be
        // far less than the ~1 MiB total of streamed input.
        Assert.True(text.Length < 4096, $"Result was {text.Length} chars, expected < 4096");
    }
}
