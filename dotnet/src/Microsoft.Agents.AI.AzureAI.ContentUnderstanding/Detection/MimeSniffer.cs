// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Detects a media type from the leading bytes of an attachment payload.
/// </summary>
/// <remarks>
/// Byte-signature only — never parses payloads. Covers the supported file types: PDF, PNG,
/// JPEG, MP3, MP4, WAV, FLAC, OGG.
/// See <c>features/sdk/dotnet-cu-context-provider/dev-plan-dotnet-cu-context-provider.md</c>
/// "Phase 3".
/// </remarks>
internal static class MimeSniffer
{
    /// <summary>
    /// The number of leading payload bytes a caller should pass to <see cref="Detect"/> for
    /// reliable detection of every supported type. Most signatures need 12 bytes or fewer, but MP3
    /// detection validates a full MPEG audio frame and then confirms a second sync word one frame
    /// later (double-sync). The largest possible MPEG frame is ~2881 bytes, so 4096 gives headroom
    /// for that frame plus a small leading ID3v2 tag.
    /// </summary>
    internal const int RecommendedHeadByteCount = 4096;

    /// <summary>
    /// Returns the detected media type, or <see langword="null"/> when the head bytes do not
    /// match a known signature.
    /// </summary>
    /// <param name="head">
    /// The leading bytes of the payload. Most signatures need only the first 12 bytes; MP3
    /// detection benefits from up to <see cref="RecommendedHeadByteCount"/> bytes (see that field's
    /// remarks).
    /// </param>
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

        // FLAC magic: "fLaC" (bare stream, i.e. not wrapped in an ID3v2 tag).
        if (StartsWith(head, [(byte)'f', (byte)'L', (byte)'a', (byte)'C']))
        {
            return "audio/flac";
        }

        // OGG container (Opus / Vorbis): "OggS" (bare stream, not ID3-wrapped).
        if (StartsWith(head, [(byte)'O', (byte)'g', (byte)'g', (byte)'S']))
        {
            return "audio/ogg";
        }

        // ID3v2 tag: parse the header length to peek at the actual audio frame
        // that follows the tag, so we can distinguish MP3 from FLAC/OGG etc.
        if (StartsWith(head, [0x49, 0x44, 0x33]) && head.Length >= 10) // "ID3"
        {
            // ID3v2 major version lives in head[3]. Only v2.2/2.3/2.4 have a
            // defined header layout we can reason about; any other (or unknown,
            // higher) version uses bytes we don't understand, so we must not
            // derive a tag size from it. Bail out of the ID3 path in that case.
            byte id3Major = head[3];
            if (id3Major < 2 || id3Major > 4)
            {
                return null;
            }

            // Extended-header flag (bit 6 of the flags byte, head[5]). Its size
            // field differs across versions: for ID3v2.3 it is *not* synchsafe and
            // whether it counts toward the body size is implementation/interpretation
            // dependent, so we can't reliably skip past it using the body size below.
            // Rather than risk pointing afterTag into the tag body (and mis-reading
            // fLaC/OggS/an MP3 sync word), treat "extended header present" as
            // "cannot decide" and return null.
            if ((head[5] & 0x40) != 0)
            {
                return null;
            }

            // Bytes 6-9 are a 28-bit synchsafe integer giving the tag body size.
            // Total tag size = 10 (header) + body size. With the extended-header
            // case already rejected above, the body size points straight at the
            // audio frame that follows the tag.
            int tagSize = 10
                + ((head[6] & 0x7F) << 21)
                + ((head[7] & 0x7F) << 14)
                + ((head[8] & 0x7F) << 7)
                + (head[9] & 0x7F);

            // ID3v2.4 footer flag: bit 4 of flags byte (head[5]) indicates
            // a 10-byte footer is appended after the tag body. This bit only
            // carries that meaning in v2.4 — in v2.2/v2.3 it is reserved/undefined,
            // so guard on the major version to avoid mis-computing the tag size.
            if (id3Major == 4 && (head[5] & 0x10) != 0)
            {
                tagSize += 10;
            }

            // A valid ID3v2 tag can legitimately exceed the head buffer (e.g. an MP3
            // with an embedded album-art frame). When the tag body — plus the bytes
            // we need to inspect right after it — does not fit in the provided head,
            // we simply lack the bytes to look past the tag and tell MP3 from
            // FLAC/OGG/etc. Treat this as "too few head bytes to decide", not as an
            // invalid signature. Callers wanting reliable detection of such files
            // should pass more leading bytes (see RecommendedHeadByteCount remarks).
            //
            // Derive the required count from the longest prefix the checks below
            // actually compare (fLaC / OggS = 4 bytes; the MP3 sync word = 2 bytes),
            // so this bound stays in lockstep with those StartsWith calls — relaxing
            // it would otherwise let StartsWith silently return false and mis-classify
            // ID3-wrapped FLAC/OGG as null.
            //
            // Compare via subtraction (head.Length is already >= 10 here, see the
            // "ID3" check above) so we never form tagSize + N and risk integer
            // overflow if the tag-size bound ever grows.
            const int AfterTagInspectBytes = 4; // max(fLaC/OggS = 4, MP3 sync = 2)
            if (head.Length - AfterTagInspectBytes < tagSize)
            {
                return null;
            }

            var afterTag = head.Slice(tagSize);

            // FLAC magic: "fLaC"
            if (StartsWith(afterTag, [(byte)'f', (byte)'L', (byte)'a', (byte)'C']))
            {
                return "audio/flac";
            }

            // OGG container (Opus / Vorbis): "OggS"
            if (StartsWith(afterTag, [(byte)'O', (byte)'g', (byte)'g', (byte)'S']))
            {
                return "audio/ogg";
            }

            // Only assume MPEG audio (MP3) when an MPEG audio frame sync word
            // actually follows the ID3v2 tag: first byte 0xFF, second byte's
            // top 3 bits all 1. Other formats (e.g. AAC/ADTS) can also carry an
            // ID3v2 tag, so without the sync word we cannot reliably claim MP3.
            if (afterTag.Length >= 2 && afterTag[0] == 0xFF && (afterTag[1] & 0xE0) == 0xE0)
            {
                return "audio/mpeg";
            }

            return null;
        }

        // MP4 / ISO BMFF: "ftyp" box marker at offset 4. Checked before the MPEG
        // frame heuristic so this strong magic wins over the byte-pattern-based
        // sync detection (an unusual box size could otherwise look like a sync word).
        if (head.Length >= 12 && head.Slice(4, 4).SequenceEqual([(byte)'f', (byte)'t', (byte)'y', (byte)'p']))
        {
            // Check major_brand at offset 8-11 for common audio-only brands.
            var majorBrand = head.Slice(8, 4);
            if (majorBrand.SequenceEqual([(byte)'M', (byte)'4', (byte)'A', (byte)' '])
                || majorBrand.SequenceEqual([(byte)'M', (byte)'4', (byte)'B', (byte)' ']))
            {
                return "audio/mp4";
            }

            return "video/mp4";
        }

        // WAV: "RIFF????WAVE". Also a strong magic, checked before the MPEG heuristic.
        if (head.Length >= 12
            && StartsWith(head, [0x52, 0x49, 0x46, 0x46])
            && head.Slice(8, 4).SequenceEqual([(byte)'W', (byte)'A', (byte)'V', (byte)'E']))
        {
            return "audio/wav";
        }

        // MPEG audio frame sync: validate the frame header and confirm a second
        // sync word follows at the computed frame length (double-sync). This makes
        // the bare detection robust against arbitrary binary data that merely
        // happens to start with a valid-looking sync word.
        if (IsMpegAudioFrame(head))
        {
            return "audio/mpeg";
        }

        return null;
    }

    /// <summary>
    /// Verifies that <paramref name="head"/> begins with a valid MPEG audio frame
    /// header, then confirms a second sync word appears at the computed frame
    /// length (double-sync). Returns <see langword="false"/> when the buffer is too
    /// short to perform the second-sync check, since a single sync word alone is
    /// not a reliable signature.
    /// </summary>
    private static bool IsMpegAudioFrame(ReadOnlySpan<byte> head)
    {
        if (!TryGetMpegFrameLength(head, out int frameLength))
        {
            return false;
        }

        // Confirm a second valid sync word sits exactly one frame away.
        if (head.Length < frameLength + 2)
        {
            // Cannot perform the double-sync check; refuse to claim MP3.
            return false;
        }

        var next = head.Slice(frameLength);
        return next[0] == 0xFF && (next[1] & 0xE0) == 0xE0;
    }

    /// <summary>
    /// Parses an MPEG audio frame header (4 bytes) and computes its length in
    /// bytes. Returns <see langword="false"/> for reserved / invalid headers.
    /// </summary>
    private static bool TryGetMpegFrameLength(ReadOnlySpan<byte> head, out int frameLength)
    {
        frameLength = 0;

        if (head.Length < 4 || head[0] != 0xFF || (head[1] & 0xE0) != 0xE0)
        {
            return false;
        }

        int versionId = (head[1] >> 3) & 0x03; // 00=MPEG2.5, 01=reserved, 10=MPEG2, 11=MPEG1
        int layerBits = (head[1] >> 1) & 0x03; // 00=reserved, 01=L3, 10=L2, 11=L1
        int bitrateIdx = (head[2] >> 4) & 0x0F; // 0000 / 1111 reserved
        int sampleRateIdx = (head[2] >> 2) & 0x03; // 11 reserved
        int padding = (head[2] >> 1) & 0x01;

        if (versionId == 0x01 || layerBits == 0x00 || bitrateIdx == 0x00
            || bitrateIdx == 0x0F || sampleRateIdx == 0x03)
        {
            return false;
        }

        bool isMpeg1 = versionId == 0x03;
        int layer = 4 - layerBits; // L1=1, L2=2, L3=3

        // Bitrate tables (kbps), indexed by bitrateIdx (1..14).
        // Index 0 is "free" and 15 is reserved (both already rejected above).
        ReadOnlySpan<int> mpeg1L1 = [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 0];
        ReadOnlySpan<int> mpeg1L2 = [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0];
        ReadOnlySpan<int> mpeg1L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0];
        ReadOnlySpan<int> mpeg2L1 = [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0];
        ReadOnlySpan<int> mpeg2L23 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0];

        // layer is always 1/2/3 (layerBits == 0 is rejected above), so the trailing discard arm
        // only ever serves MPEG2/2.5 Layer 2/3; it also makes the switch exhaustive for the
        // compiler (the (isMpeg1, layer) tuple is otherwise open-ended).
        int bitrate = (isMpeg1, layer) switch
        {
            (true, 1) => mpeg1L1[bitrateIdx],
            (true, 2) => mpeg1L2[bitrateIdx],
            (true, 3) => mpeg1L3[bitrateIdx],
            (false, 1) => mpeg2L1[bitrateIdx],
            _ => mpeg2L23[bitrateIdx],
        };
        bitrate *= 1000; // kbps -> bps

        // Sample rate tables (Hz), indexed by sampleRateIdx (0..2).
        ReadOnlySpan<int> mpeg1Rates = [44100, 48000, 32000];
        ReadOnlySpan<int> mpeg2Rates = [22050, 24000, 16000];
        ReadOnlySpan<int> mpeg25Rates = [11025, 12000, 8000];
        int sampleRate = versionId switch
        {
            0x03 => mpeg1Rates[sampleRateIdx],
            0x02 => mpeg2Rates[sampleRateIdx],
            _ => mpeg25Rates[sampleRateIdx], // MPEG 2.5
        };

        if (bitrate == 0 || sampleRate == 0)
        {
            return false;
        }

        if (layer == 1)
        {
            frameLength = ((12 * bitrate / sampleRate) + padding) * 4;
        }
        else
        {
            // MPEG2/2.5 (low-sampling-rate extension) uses 72 samples-per-frame for
            // both Layer 2 and Layer 3 (576 samples); everything else uses 144.
            int samplesFactor = (!isMpeg1 && layer != 1) ? 72 : 144;
            // No int overflow possible: samplesFactor <= 144 and bitrate <= 448000,
            // so the product (<= 64,512,000) stays well within int range. Revisit if
            // the bitrate tables are ever extended beyond the current MPEG spec.
            frameLength = (samplesFactor * bitrate / sampleRate) + padding;
        }

        return frameLength > 4;
    }

    private static bool StartsWith(ReadOnlySpan<byte> data, ReadOnlySpan<byte> prefix) =>
        data.Length >= prefix.Length && data.Slice(0, prefix.Length).SequenceEqual(prefix);
}
