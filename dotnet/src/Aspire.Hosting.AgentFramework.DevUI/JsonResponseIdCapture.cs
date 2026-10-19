// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Text.Json;

namespace Aspire.Hosting.AgentFramework;

/// <summary>
/// Captures a top-level response ID from a bounded JSON prefix without buffering the response body.
/// </summary>
internal sealed class JsonResponseIdCapture
{
    private const int MaxPrefixLength = 64 * 1024;
    private readonly ArrayBufferWriter<byte> _prefix = new(MaxPrefixLength);
    private bool _truncated;

    /// <summary>
    /// Retains up to 64 KiB of the response, ignoring subsequent bytes.
    /// </summary>
    /// <param name="bytes">The next fragment read from the proxied response.</param>
    internal void Append(ReadOnlySpan<byte> bytes)
    {
        var length = Math.Min(bytes.Length, MaxPrefixLength - this._prefix.WrittenCount);
        if (length > 0)
        {
            this._prefix.Write(bytes[..length]);
        }

        this._truncated |= length < bytes.Length;
    }

    /// <summary>
    /// Gets the captured ID after the caller has finished forwarding the response.
    /// </summary>
    /// <returns>The top-level ID, or <see langword="null"/> if it is missing from the prefix or the prefix is malformed.</returns>
    internal string? Complete()
    {
        try
        {
            var reader = new Utf8JsonReader(this._prefix.WrittenSpan, isFinalBlock: !this._truncated, state: default);
            if (!reader.Read() || reader.TokenType != JsonTokenType.StartObject)
            {
                return null;
            }

            string? responseId = null;
            var pendingId = false;
            while (reader.Read())
            {
                if (reader.TokenType == JsonTokenType.PropertyName)
                {
                    pendingId = reader.CurrentDepth == 1 && reader.ValueTextEquals("id"u8);
                    continue;
                }

                if (pendingId)
                {
                    responseId = reader.TokenType == JsonTokenType.String ? reader.GetString() : null;
                    pendingId = false;
                }
            }

            return responseId is { Length: > 0 } ? responseId : null;
        }
        catch (JsonException)
        {
            // Capture is best effort; malformed JSON must not affect the proxied response.
            return null;
        }
    }
}
