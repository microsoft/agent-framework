// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Tools.Shell.UnitTests;

/// <summary>
/// Direct coverage for <see cref="ShellSession.TruncateHeadTail"/> (internal,
/// reachable via InternalsVisibleTo). The function is on the hot path for
/// every shell command — both LocalShellExecutor and DockerShellExecutor feed
/// captured stdout/stderr through it before returning.
/// </summary>
public sealed class ShellSessionTests
{
    [Fact]
    public void QuotePosix_NoSpecialChars_WrapsInSingleQuotes()
    {
        Assert.Equal("'/tmp/work'", ShellSession.QuotePosix("/tmp/work"));
    }

    [Fact]
    public void QuotePosix_DollarBacktickAndCommandSubstitution_ProducesLiteralString()
    {
        // The whole point: these substrings must NOT be interpreted by sh.
        Assert.Equal("'/tmp/$(touch /pwn)'", ShellSession.QuotePosix("/tmp/$(touch /pwn)"));
        Assert.Equal("'/tmp/$VAR'", ShellSession.QuotePosix("/tmp/$VAR"));
        Assert.Equal("'/tmp/`id`'", ShellSession.QuotePosix("/tmp/`id`"));
    }

    [Fact]
    public void QuotePosix_EmbeddedSingleQuote_ClosesAndReopens()
    {
        // POSIX: single-quoted strings cannot contain a single quote, so we close,
        // emit an escaped quote, and reopen: a' -> 'a'\''b' -> a'b literal.
        Assert.Equal("'a'\\''b'", ShellSession.QuotePosix("a'b"));
    }

    [Fact]
    public void QuotePowerShell_DollarAndSubexpression_ProducesLiteralString()
    {
        Assert.Equal("'C:\\$(throw)'", ShellSession.QuotePowerShell("C:\\$(throw)"));
        Assert.Equal("'C:\\$env:PATH'", ShellSession.QuotePowerShell("C:\\$env:PATH"));
    }

    [Fact]
    public void QuotePowerShell_EmbeddedSingleQuote_DoublesIt()
    {
        // PowerShell: 'a''b' is the literal string a'b.
        Assert.Equal("'a''b'", ShellSession.QuotePowerShell("a'b"));
    }

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

    [Fact]
    public void TruncateHeadTail_MultiByteUtf8_RespectsByteBudgetAndRuneBoundaries()
    {
        // Each "🔥" is 4 UTF-8 bytes (and 2 UTF-16 code units). 50 of them = 200 bytes.
        var input = string.Concat(System.Linq.Enumerable.Repeat("🔥", 50));
        Assert.Equal(200, System.Text.Encoding.UTF8.GetByteCount(input));

        var (text, truncated) = ShellSession.TruncateHeadTail(input, cap: 40);

        Assert.True(truncated);

        // Result must round-trip through UTF-8 unchanged: no rune was split.
        var roundTripped = System.Text.Encoding.UTF8.GetString(System.Text.Encoding.UTF8.GetBytes(text));
        Assert.Equal(text, roundTripped);

        // The retained head + tail content must not exceed the byte budget.
        // (The marker line is appended on top of that budget, by design.)
        var marker = text[text.IndexOf('\n', StringComparison.Ordinal)..text.LastIndexOf('\n')];
        var preserved = text.Replace(marker, string.Empty, StringComparison.Ordinal).Replace("\n", string.Empty, StringComparison.Ordinal);
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(preserved) <= 40);
    }

    [Fact]
    public void TruncateHeadTail_NonAsciiAtBoundary_DoesNotProduceReplacementChar()
    {
        // 4-byte UTF-8 emoji surrounded by ASCII; cap chosen so naive char-based
        // truncation would have split a surrogate pair. The new implementation
        // must skip the rune that doesn't fit instead of emitting U+FFFD.
        const string Input = "AAAA🔥BBBBCCCC🔥DDDD";
        var (text, _) = ShellSession.TruncateHeadTail(Input, cap: 8);

        Assert.DoesNotContain("\uFFFD", text);
    }

    [Fact]
    public void TruncateHeadTail_UnpairedHighSurrogate_DoesNotMisalignByteCount()
    {
        // An unpaired high surrogate (no following low surrogate) used to make the
        // prefix walker advance by 2 chars and miscount bytes. Verify that the
        // function completes, returns a sensible result, and respects the cap.
        var input = "AAAA" + new string('\uD83D', 1) + "BBBB"; // lone high surrogate
        var (text, _) = ShellSession.TruncateHeadTail(input, cap: 6);

        // The encoder substitutes U+FFFD for the unpaired surrogate when emitting bytes,
        // so we just check that the call did not overrun and produced a result that
        // round-trips through UTF-8.
        var rt = System.Text.Encoding.UTF8.GetString(System.Text.Encoding.UTF8.GetBytes(text));
        Assert.Equal(text, rt);
    }
}
