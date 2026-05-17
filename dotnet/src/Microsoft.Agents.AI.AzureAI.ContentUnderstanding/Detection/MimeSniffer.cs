// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Detects a media type from the leading bytes of an attachment payload.
/// </summary>
/// <remarks>
/// Byte-signature only — never parses payloads. Mirrors the supported file types listed in
/// the Python provider's <c>MEDIA_TYPE_ANALYZER_MAP</c>: PDF, PNG, JPEG, MP3, MP4, WAV.
/// See <c>features/sdk/dotnet-cu-context-provider/dev-plan-dotnet-cu-context-provider.md</c>
/// "Phase 3".
/// </remarks>
internal static class MimeSniffer
{
    /// <summary>
    /// Returns the detected media type, or <see langword="null"/> when the head bytes do not
    /// match a known signature.
    /// </summary>
    /// <param name="head">The leading bytes of the payload (at least the first 12 are useful; more is fine).</param>
    public static string? Detect(ReadOnlySpan<byte> head)
    {
        if (StartsWith(head, [0x25, 0x50, 0x44, 0x46, 0x2D])) // "%PDF-"
        {
            return "application/pdf";
        }

        if (StartsWith(head, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]))
        {
            return "image/png";
        }

        if (StartsWith(head, [0xFF, 0xD8, 0xFF]))
        {
            return "image/jpeg";
        }

        if (StartsWith(head, [0x49, 0x44, 0x33])) // "ID3"
        {
            return "audio/mpeg";
        }

        // MPEG audio frame sync: first byte 0xFF, second byte's top 3 bits all 1.
        if (head.Length >= 2 && head[0] == 0xFF && (head[1] & 0xE0) == 0xE0)
        {
            return "audio/mpeg";
        }

        // MP4 / ISO BMFF: "ftyp" box marker at offset 4.
        if (head.Length >= 8 && head.Slice(4, 4).SequenceEqual([(byte)'f', (byte)'t', (byte)'y', (byte)'p']))
        {
            return "video/mp4";
        }

        // WAV: "RIFF????WAVE"
        if (head.Length >= 12
            && StartsWith(head, [0x52, 0x49, 0x46, 0x46])
            && head.Slice(8, 4).SequenceEqual([(byte)'W', (byte)'A', (byte)'V', (byte)'E']))
        {
            return "audio/wav";
        }

        return null;
    }

    private static bool StartsWith(ReadOnlySpan<byte> data, ReadOnlySpan<byte> prefix) =>
        data.Length >= prefix.Length && data.Slice(0, prefix.Length).SequenceEqual(prefix);
}
