// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Bounded accumulator that keeps the first <c>cap/2</c> characters of input and the
/// most recent <c>cap/2</c> characters (rolling tail). When the input fits in
/// <c>cap</c>, the result is the original concatenation. Otherwise the middle is
/// dropped and the result includes a "[... truncated N chars ...]" marker. Memory
/// usage is bounded at roughly <c>cap</c> regardless of how much is appended.
/// </summary>
/// <remarks>
/// Used by <see cref="LocalShellTool"/> and <see cref="DockerShellTool"/> when
/// streaming stdout / stderr from a long-running subprocess to avoid OOM on
/// chatty commands.
/// </remarks>
internal sealed class HeadTailBuffer
{
    private readonly int _cap;
    private readonly int _halfCap;
    private readonly StringBuilder _head = new();
    private readonly Queue<char> _tail = new();
    private long _totalChars;

    public HeadTailBuffer(int cap)
    {
        this._cap = cap;
        this._halfCap = cap / 2;
    }

    public void AppendLine(string line)
    {
        this.AppendInternal(line);
        this.AppendInternal("\n");
    }

    private void AppendInternal(string s)
    {
        for (var i = 0; i < s.Length; i++)
        {
            this._totalChars++;
            if (this._head.Length < this._halfCap)
            {
                _ = this._head.Append(s[i]);
            }
            else
            {
                this._tail.Enqueue(s[i]);
                if (this._tail.Count > this._halfCap)
                {
                    _ = this._tail.Dequeue();
                }
            }
        }
    }

    public (string text, bool truncated) ToFinalString()
    {
        if (this._totalChars <= this._cap)
        {
            var combined = new StringBuilder(this._head.Length + this._tail.Count);
            _ = combined.Append(this._head);
            foreach (var c in this._tail)
            {
                _ = combined.Append(c);
            }
            return (combined.ToString(), false);
        }

        var dropped = this._totalChars - this._head.Length - this._tail.Count;
        var sb = new StringBuilder();
        _ = sb.Append(this._head);
        _ = sb.Append('\n');
        _ = sb.Append("[... truncated ").Append(dropped).Append(" chars ...]");
        _ = sb.Append('\n');
        foreach (var c in this._tail)
        {
            _ = sb.Append(c);
        }
        return (sb.ToString(), true);
    }
}
