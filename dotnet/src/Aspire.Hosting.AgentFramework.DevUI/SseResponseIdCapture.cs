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
                this.ProcessLine(this._lineBuffer.WrittenSpan, isFinalBlock: false);
                if (this.ResponseId is not null)
                {
                    return;
                }

                this._lineBuffer.Clear();
                this._discardingOversizedLine = true;
                continue;
            }

            this._lineBuffer.GetSpan(1)[0] = value;
            this._lineBuffer.Advance(1);
        }
    }

    private void ProcessLine(ReadOnlySpan<byte> line, bool isFinalBlock = true)
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
            var reader = new Utf8JsonReader(line, isFinalBlock, state: default);
            var responseObjectDepth = -1;
            var pendingResponseObject = false;
            var pendingResponseId = false;
            var pendingDirectId = false;
            string? nestedResponseId = null;
            string? directResponseId = null;

            while (reader.Read())
            {
                if (reader.TokenType == JsonTokenType.PropertyName)
                {
                    pendingResponseObject = reader.CurrentDepth == 1 && reader.ValueTextEquals("response"u8);
                    pendingResponseId = reader.CurrentDepth == responseObjectDepth && reader.ValueTextEquals("id"u8);
                    pendingDirectId = reader.CurrentDepth == 1 && reader.ValueTextEquals("id"u8);
                    continue;
                }

                if (reader.TokenType == JsonTokenType.StartObject && pendingResponseObject)
                {
                    responseObjectDepth = reader.CurrentDepth + 1;
                }
                else if (reader.TokenType == JsonTokenType.EndObject &&
                    responseObjectDepth == reader.CurrentDepth + 1)
                {
                    responseObjectDepth = -1;
                }
                else if (reader.TokenType == JsonTokenType.String && (pendingResponseId || pendingDirectId))
                {
                    var responseId = reader.GetString();
                    if (pendingResponseId)
                    {
                        nestedResponseId = responseId;
                    }
                    else if (responseId?.StartsWith("resp_", StringComparison.Ordinal) == true)
                    {
                        directResponseId = responseId;
                    }
                }

                pendingResponseObject = false;
                pendingResponseId = false;
                pendingDirectId = false;
            }

            this.ResponseId = nestedResponseId ?? directResponseId;
        }
        catch (JsonException)
        {
            // A malformed SSE event must not prevent a later valid response event from being captured.
        }
    }
}
