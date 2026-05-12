// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Coverage for <see cref="HeadTailBuffer"/>, the bounded stdout/stderr accumulator
/// shared by <see cref="LocalShellExecutor"/> and <see cref="DockerShellExecutor"/>.
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
        // Result must respect the byte cap (allow some overhead for the marker line).
        var byteCount = System.Text.Encoding.UTF8.GetByteCount(text);
        Assert.True(byteCount <= 4096 + 128, $"Result was {byteCount} bytes, expected <= ~{4096 + 128}");
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
        // The exact upper bound depends on marker formatting, but it must be far
        // less than the ~1 MiB total of streamed input.
        var byteCount = System.Text.Encoding.UTF8.GetByteCount(text);
        Assert.True(byteCount < 4096, $"Result was {byteCount} bytes, expected < 4096");
    }

    [Fact]
    public void Append_MultiByteUtf8_RespectsByteBudgetAndNeverSplitsRunes()
    {
        // Each "🔥" is 4 UTF-8 bytes (and 2 UTF-16 code units). A char-based
        // buffer using Queue<char> would happily split a surrogate pair when
        // capacity ran out, leaving an unpaired surrogate (U+FFFD on decode).
        var buf = new HeadTailBuffer(cap: 32);
        for (var i = 0; i < 200; i++)
        {
            buf.AppendLine("🔥🔥🔥🔥🔥");
        }

        var (text, truncated) = buf.ToFinalString();

        Assert.True(truncated);

        // Result must round-trip through UTF-8 unchanged: no rune was split.
        var roundTripped = System.Text.Encoding.UTF8.GetString(System.Text.Encoding.UTF8.GetBytes(text));
        Assert.Equal(text, roundTripped);

        Assert.DoesNotContain("\uFFFD", text);
    }

    [Fact]
    public void Append_OddCap_RoundTripsExactlyAtCapWithoutDropping()
    {
        // With the previous design (cap/2 for both halves), an odd cap could
        // drop a byte while still reporting truncated == false. Verify that an
        // input whose UTF-8 size is exactly `cap` round-trips losslessly.
        const string Input = "ABCDE"; // 5 bytes
        var buf = new HeadTailBuffer(cap: 6);
        buf.AppendLine(Input); // 5 + '\n' = 6 bytes, exactly at cap
        var (text, truncated) = buf.ToFinalString();

        Assert.False(truncated);
        Assert.Equal(Input + "\n", text);
    }

    [Fact]
    public void Append_OddCap_AtCap_NoSilentDataDrop()
    {
        // Reviewer's exact scenario: cap=5. Push exactly 5 bytes of input.
        // halfCap-based design would silently drop a byte while reporting
        // truncated == false. With separate head/tail budgets, all 5 bytes
        // must be retained.
        var buf = new HeadTailBuffer(cap: 5);
        // AppendLine adds a trailing newline, so feed 4 chars to land at exactly 5 bytes.
        buf.AppendLine("ABCD");
        var (text, truncated) = buf.ToFinalString();

        Assert.False(truncated);
        Assert.Equal("ABCD\n", text);
    }
}
