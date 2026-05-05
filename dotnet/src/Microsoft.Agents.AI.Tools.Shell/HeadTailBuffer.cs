// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Bounded accumulator that keeps the first <c>cap/2</c> UTF-8 bytes of input and
/// the most recent <c>cap/2</c> UTF-8 bytes (rolling tail). When the input fits in
/// <c>cap</c> bytes, the result is the original concatenation. Otherwise the middle
/// is dropped and the result includes a "[... truncated N bytes ...]" marker.
/// </summary>
/// <remarks>
/// <para>
/// Used by <see cref="LocalShellTool"/> and <see cref="DockerShellTool"/> when
/// streaming stdout / stderr from a long-running subprocess. Memory usage is bounded
/// at roughly <c>cap</c> bytes regardless of how much is appended.
/// </para>
/// <para>
/// The buffer counts UTF-8 bytes (matching the public <c>maxOutputBytes</c> contract
/// and <see cref="ShellSession.TruncateHeadTail"/>). Append happens one rune at a time
/// — when the head fills, the next rune's UTF-8 bytes go to the tail as an indivisible
/// unit, and the oldest rune is dropped from the tail. This guarantees the final
/// string never contains a split rune (no orphan surrogates, no invalid UTF-8).
/// </para>
/// </remarks>
internal sealed class HeadTailBuffer
{
    private readonly int _cap;
    private readonly int _halfCap;
    private readonly List<byte> _head = new();
    // Tail is a queue of complete rune-byte-sequences so we can drop oldest rune
    // atomically when capacity is exceeded.
    private readonly Queue<byte[]> _tail = new();
    private int _tailBytes;
    private long _totalBytes;

    public HeadTailBuffer(int cap)
    {
        this._cap = cap < 0 ? 0 : cap;
        this._halfCap = this._cap / 2;
    }

    public void AppendLine(string line)
    {
        this.AppendInternal(line);
        this.AppendInternal("\n");
    }

    private void AppendInternal(string s)
    {
        Span<byte> scratch = stackalloc byte[4];
        foreach (var rune in s.EnumerateRunes())
        {
            // Encode this rune to its UTF-8 bytes (1-4 bytes).
            var n = rune.EncodeToUtf8(scratch);
            this._totalBytes += n;

            if (this._head.Count + n <= this._halfCap)
            {
                for (var i = 0; i < n; i++) { this._head.Add(scratch[i]); }
                continue;
            }

            // Head is full — append to tail as a single rune-sized chunk.
            var bytes = scratch[..n].ToArray();
            this._tail.Enqueue(bytes);
            this._tailBytes += n;

            // Evict whole runes from the front of the tail until we fit.
            while (this._tailBytes > this._halfCap && this._tail.Count > 0)
            {
                var dropped = this._tail.Dequeue();
                this._tailBytes -= dropped.Length;
            }
        }
    }

    public (string text, bool truncated) ToFinalString()
    {
        if (this._totalBytes <= this._cap)
        {
            var combinedBytes = new byte[this._head.Count + this._tailBytes];
            this._head.CopyTo(combinedBytes, 0);
            var offset = this._head.Count;
            foreach (var chunk in this._tail)
            {
                Array.Copy(chunk, 0, combinedBytes, offset, chunk.Length);
                offset += chunk.Length;
            }
            return (Encoding.UTF8.GetString(combinedBytes), false);
        }

        var dropped = this._totalBytes - this._head.Count - this._tailBytes;
        var headStr = Encoding.UTF8.GetString(this._head.ToArray());
        var tailBytes = new byte[this._tailBytes];
        var tailOffset = 0;
        foreach (var chunk in this._tail)
        {
            Array.Copy(chunk, 0, tailBytes, tailOffset, chunk.Length);
            tailOffset += chunk.Length;
        }
        var tailStr = Encoding.UTF8.GetString(tailBytes);

        var sb = new StringBuilder(headStr.Length + tailStr.Length + 64);
        _ = sb.Append(headStr);
        _ = sb.Append('\n');
        _ = sb.Append("[... truncated ").Append(dropped).Append(" bytes ...]");
        _ = sb.Append('\n');
        _ = sb.Append(tailStr);
        return (sb.ToString(), true);
    }
}
