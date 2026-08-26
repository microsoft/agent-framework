// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Text.Json;

namespace Aspire.Hosting.AgentFramework;

/// <summary>
/// Incrementally extracts an OpenAI response ID from an SSE response without delaying proxy writes.
/// </summary>
internal sealed class SseResponseIdCapture
{
    private const int MaxLineLength = 64 * 1024;
    private readonly ArrayBufferWriter<byte> _lineBuffer = new();
    private bool _discardingOversizedLine;

    /// <summary>
    /// Gets the first response ID observed in the stream.
    /// </summary>
    internal string? ResponseId { get; private set; }

    /// <summary>
    /// Adds another raw SSE response fragment to the parser.
    /// </summary>
    /// <param name="bytes">The next bytes read from the proxied response.</param>
    internal void Append(ReadOnlySpan<byte> bytes)
    {
        if (this.ResponseId is not null)
        {
            return;
        }

        foreach (var value in bytes)
        {
            if (value == (byte)'\n')
            {
                if (!this._discardingOversizedLine)
                {
                    this.ProcessLine(this._lineBuffer.WrittenSpan);
                }

                this._lineBuffer.Clear();
                this._discardingOversizedLine = false;

                if (this.ResponseId is not null)
                {
                    return;
                }

                continue;
            }

            if (this._discardingOversizedLine)
            {
                continue;
            }

            if (this._lineBuffer.WrittenCount >= MaxLineLength)
            {
                this._lineBuffer.Clear();
                this._discardingOversizedLine = true;
                continue;
            }

            this._lineBuffer.GetSpan(1)[0] = value;
            this._lineBuffer.Advance(1);
        }
    }

    private void ProcessLine(ReadOnlySpan<byte> line)
    {
        if (!line.IsEmpty && line[^1] == (byte)'\r')
        {
            line = line[..^1];
        }

        ReadOnlySpan<byte> dataPrefix = "data:"u8;
        if (!line.StartsWith(dataPrefix))
        {
            return;
        }

        line = line[dataPrefix.Length..].TrimStart((byte)' ');
        if (line.SequenceEqual("[DONE]"u8))
        {
            return;
        }

        try
        {
            using var document = JsonDocument.Parse(line.ToArray());
            var root = document.RootElement;

            if (root.TryGetProperty("response", out var response) &&
                response.ValueKind == JsonValueKind.Object &&
                response.TryGetProperty("id", out var responseId) &&
                responseId.ValueKind == JsonValueKind.String)
            {
                this.ResponseId = responseId.GetString();
                return;
            }

            if (root.TryGetProperty("id", out var id) &&
                id.ValueKind == JsonValueKind.String &&
                id.GetString() is { } directId &&
                directId.StartsWith("resp_", StringComparison.Ordinal))
            {
                this.ResponseId = directId;
            }
        }
        catch (JsonException)
        {
            // A malformed SSE event must not prevent a later valid response event from being captured.
        }
    }
}
