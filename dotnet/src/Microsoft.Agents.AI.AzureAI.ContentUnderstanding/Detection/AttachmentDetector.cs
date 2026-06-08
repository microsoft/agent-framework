// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics;
#if NET8_0_OR_GREATER
using System.Diagnostics.CodeAnalysis;
#endif
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// One attachment found in a turn's <see cref="ChatMessage"/> stream that the provider intends
/// to analyze.
/// </summary>
/// <param name="OriginalContent">The original <see cref="AIContent"/> node from the message (kept so the caller can locate it for replacement).</param>
/// <param name="ResolvedMediaType">The final media type used to pick an analyzer.</param>
/// <param name="Filename">The display filename used in tool responses and renderer metadata.</param>
/// <param name="Data">Raw bytes when the attachment is a <see cref="DataContent"/>; <see langword="null"/> when it's a <see cref="UriContent"/>.</param>
/// <param name="Uri">Remote URI when the attachment is a <see cref="UriContent"/>; <see langword="null"/> when it's a <see cref="DataContent"/>.</param>
internal sealed record DetectedAttachment(
    AIContent OriginalContent,
    string ResolvedMediaType,
    string Filename,
    byte[]? Data,
    Uri? Uri);

/// <summary>
/// Extracts <see cref="DetectedAttachment"/> entries from a turn's <see cref="ChatMessage"/> stream.
/// </summary>
/// <remarks>
/// Unsupported content silently skips (must never block the agent run). Filename resolution
/// order: <see cref="DataContent.Name"/> → <see cref="AIContent.AdditionalProperties"/>["filename"]
/// → synthesized <c>attachment-{sha256[0..12]}.{ext}</c>. Supported media types cover documents,
/// images, text, audio, and video per the Azure CU input file limits:
/// https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits.
/// </remarks>
internal static class AttachmentDetector
{
    private const string OctetStream = "application/octet-stream";

    // Allow-list of supported media types. Comparisons are case-insensitive (OrdinalIgnoreCase).
    // audio/wave and audio/x-wav are accepted as WAV aliases up front for maximum tolerance of
    // HTTP-server-supplied types.
    private static readonly HashSet<string> s_supportedMediaTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        // Documents and images
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/bmp",
        "image/heif",
        "image/heic",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        // Text
        "text/plain",
        "text/html",
        "text/markdown",
        "text/rtf",
        "text/xml",
        "application/xml",
        "message/rfc822",
        "application/vnd.ms-outlook",
        // Audio
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/m4a",
        "audio/flac",
        "audio/ogg",
        "audio/opus",
        "audio/webm",
        "audio/x-ms-wma",
        "audio/aac",
        "audio/amr",
        "audio/3gpp",
        // Video
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/webm",
        "video/x-flv",
        "video/x-ms-wmv",
        "video/x-ms-asf",
        "video/x-matroska",
    };

    public static IEnumerable<DetectedAttachment> Detect(IEnumerable<ChatMessage> messages)
    {
        if (messages is null)
        {
            yield break;
        }

        foreach (ChatMessage message in messages)
        {
            if (message?.Contents is null)
            {
                continue;
            }

            foreach (AIContent content in message.Contents)
            {
                DetectedAttachment? detected = TryDetect(content);
                if (detected is not null)
                {
                    yield return detected;
                }
            }
        }
    }

    private static DetectedAttachment? TryDetect(AIContent content)
    {
        switch (content)
        {
            case DataContent dc:
                return TryDetectData(dc);
            case UriContent uc:
                return TryDetectUri(uc);
            default:
                return null;
        }
    }

    private static DetectedAttachment? TryDetectData(DataContent dc)
    {
        // Resolve the media type from the head bytes BEFORE materializing the full payload, so an
        // unsupported (or unknown-but-unsniffable) large attachment is rejected without copying
        // potentially hundreds of MB. Sniffing is also skipped entirely when the supplied type is a
        // concrete, non-octet-stream value (sniff only feeds the octet-stream / empty fallback).
        ReadOnlyMemory<byte> data = dc.Data;
        string supplied = BaseMediaType(dc.MediaType);
        bool isOctetStream = string.Equals(supplied, OctetStream, StringComparison.OrdinalIgnoreCase);
        bool needSniff = data.Length > 0 && (supplied.Length == 0 || isOctetStream);
        string? sniffed = needSniff ? MimeSniffer.Detect(SliceHead(data.Span)) : null;

        // Treat octet-stream as "unknown — fall back to sniff".
        string resolved = isOctetStream
            ? (sniffed ?? string.Empty)
            : (!string.IsNullOrEmpty(supplied) ? supplied : sniffed ?? string.Empty);

        // No usable media type (supplied empty/octet-stream AND sniff produced nothing) → skip.
        // Made explicit so the short-circuit doesn't rely on the allow-list never containing "".
        if (string.IsNullOrEmpty(resolved))
        {
            return null;
        }

        if (!s_supportedMediaTypes.Contains(resolved))
        {
            // Unknown / unsupported → silently skip; must never block the agent run.
            return null;
        }

        // Supported → now materialize a private copy (DetectedAttachment.Data is held across turns,
        // so a defensive copy avoids aliasing the caller's buffer).
        byte[] bytes = data.ToArray();
        string filename = ResolveDataFilename(dc, resolved, bytes);
        return new DetectedAttachment(dc, resolved, filename, bytes, null);
    }

    private static DetectedAttachment? TryDetectUri(UriContent uc)
    {
        // A UriContent with no URI carries no fetchable payload → nothing to analyze; skip.
        if (uc.Uri is null)
        {
            return null;
        }

        string resolved = BaseMediaType(uc.MediaType);
        if (!s_supportedMediaTypes.Contains(resolved))
        {
            return null;
        }

        string filename = ResolveUriFilename(uc, resolved);
        return new DetectedAttachment(uc, resolved, filename, null, uc.Uri);
    }

    // Strips any RFC 2045 parameters (e.g. "; charset=utf-8") from a media type so allow-list
    // lookups match. Callers may supply parameterized types (especially UriContent.MediaType,
    // which is passed through verbatim) that would otherwise miss the exact-match HashSet.
    private static string BaseMediaType(string? mediaType)
    {
        if (string.IsNullOrEmpty(mediaType))
        {
            return string.Empty;
        }

        int semicolon = mediaType!.IndexOf(';');
        string baseType = semicolon >= 0 ? mediaType.Substring(0, semicolon) : mediaType;
        // Normalize stray whitespace (incl. interior, e.g. "application / pdf") so tolerant
        // inputs still hit the exact-match allow-list.
        return baseType.Replace(" ", string.Empty).Replace("\t", string.Empty).Trim();
    }

    private static string ResolveDataFilename(DataContent dc, string mediaType, byte[] bytes)
    {
        string? candidate = !string.IsNullOrEmpty(dc.Name)
            ? dc.Name
            : TryGetFilenameFromProperties(dc.AdditionalProperties)
                ?? TryGetFilenameFromRawRepresentation(dc.RawRepresentation);

        if (!string.IsNullOrEmpty(candidate))
        {
            string cleaned = SanitizeFilename(candidate!);
            if (!string.IsNullOrEmpty(cleaned))
            {
                return cleaned;
            }
        }

        return Synthesize(bytes, bytes.Length, mediaType);
    }

    private static string ResolveUriFilename(UriContent uc, string mediaType)
    {
        string? fromProps = TryGetFilenameFromProperties(uc.AdditionalProperties);
        if (!string.IsNullOrEmpty(fromProps))
        {
            string cleaned = SanitizeFilename(fromProps!);
            if (!string.IsNullOrEmpty(cleaned))
            {
                return cleaned;
            }
        }

        // Fall back to the URI's last segment when it looks like a real filename. Uri.Segments is
        // only valid for absolute URIs (throws InvalidOperationException otherwise), so guard on
        // IsAbsoluteUri; relative URIs skip this and fall through to the synthesized name below.
        string? last = uc.Uri.IsAbsoluteUri && uc.Uri.Segments.Length > 0 ? uc.Uri.Segments[uc.Uri.Segments.Length - 1] : null;
        last = last?.Trim('/');
        if (!string.IsNullOrEmpty(last) && last!.Contains('.'))
        {
            string cleaned = SanitizeFilename(last);
            if (!string.IsNullOrEmpty(cleaned))
            {
                return cleaned;
            }
        }

        // Synthesize from a hash of the URI when no real filename can be derived. Hash only
        // scheme+host+path (drop query/fragment) so the same resource carrying a time-bound query
        // (e.g. a rotating SAS token) yields a stable dedup prefix across turns instead of a new
        // filename each time. Relative URIs (no GetLeftPart) fall back to the full string.
        string uriKey = uc.Uri.IsAbsoluteUri ? uc.Uri.GetLeftPart(UriPartial.Path) : uc.Uri.ToString();
        byte[] uriBytes = Encoding.UTF8.GetBytes(uriKey);
        return Synthesize(uriBytes, uriBytes.Length, mediaType);
    }

    private static string? TryGetFilenameFromProperties(AdditionalPropertiesDictionary? props)
    {
        if (props is null)
        {
            return null;
        }

        if (props.TryGetValue("filename", out object? value) && value is string s && !string.IsNullOrEmpty(s))
        {
            return s;
        }

        return null;
    }

    // Hosting wrappers (e.g. Microsoft.Agents.AI.Hosting.OpenAI's Responses ItemContentInputFile)
    // attach the wire payload as DataContent.RawRepresentation but don't always propagate the
    // "filename" field onto DataContent.Name. Recover it via duck-typed reflection so we don't take
    // a hard dependency on the hosting package's internal types.
    private static readonly ConcurrentDictionary<Type, Func<object, string?>?> s_rawFilenameAccessors = new();

    private static string? TryGetFilenameFromRawRepresentation(object? raw)
    {
        if (raw is null)
        {
            return null;
        }

        Func<object, string?>? accessor = s_rawFilenameAccessors.GetOrAdd(raw.GetType(), BuildRawFilenameAccessor);
        return accessor?.Invoke(raw);
    }

    private static Func<object, string?>? BuildRawFilenameAccessor(Type type)
        => BuildRawFilenameAccessorCore(type);

#if NET8_0_OR_GREATER
    [UnconditionalSuppressMessage(
        "Trimming",
        "IL2070:'this' argument does not satisfy 'DynamicallyAccessedMembersAttribute' in call to target method.",
        Justification = "RawRepresentation types come from upstream hosting/protocol packages (e.g. Microsoft.Agents.AI.Hosting.OpenAI's ItemContentInputFile) whose public Filename property has a stable, well-known name. Failure to resolve via reflection (e.g. under aggressive trimming) is non-fatal — caller falls back to Synthesize.")]
#endif
    private static Func<object, string?>? BuildRawFilenameAccessorCore(Type type)
    {
        foreach (string name in new[] { "Filename", "FileName" })
        {
            PropertyInfo? prop = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (prop is not null && prop.PropertyType == typeof(string) && prop.CanRead)
            {
                return instance => prop.GetValue(instance) as string;
            }
        }
        return null;
    }

    private const int MaxFilenameLength = 255;

    private static readonly char[] s_spaceSplit = [' '];

    // Removes control chars, path separators, and ".." segments from a caller-supplied filename;
    // collapses whitespace runs; caps length. The resolved filename is interpolated into LLM-visible
    // markdown (AnalysisRenderer YAML front-matter "source:" and per-document vector-store notes),
    // so raw control chars / newlines / backticks would let an attacker-controlled filename break
    // those framings and inject pseudo-instructions. Returns empty when nothing usable remains;
    // caller falls back to Synthesize.
    private static string SanitizeFilename(string raw)
    {
        if (string.IsNullOrEmpty(raw))
        {
            return string.Empty;
        }

        StringBuilder sb = new(raw.Length);
        foreach (char ch in raw)
        {
            if (ch == '/' || ch == '\\' || ch < 0x20 || (ch >= 0x7F && ch <= 0x9F))
            {
                sb.Append(' ');
                continue;
            }

            sb.Append(ch);
        }

        string[] tokens = sb.ToString().Split(s_spaceSplit, StringSplitOptions.RemoveEmptyEntries);
        List<string> keep = new(tokens.Length);
        foreach (string token in tokens)
        {
            if (token == "..")
            {
                continue;
            }

            keep.Add(token);
        }

        string joined = string.Join(" ", keep);
        return joined.Length > MaxFilenameLength ? joined.Substring(0, MaxFilenameLength) : joined;
    }

    // The hash only needs to produce a stable, well-distributed dedup prefix — it is NOT a content
    // integrity check. We hash the full payload (plus its total length, mixed in to distinguish
    // same-content / different-length edge cases) so two attachments that differ only in their
    // middle bytes never collide on the dedup prefix.
    private static string Synthesize(ReadOnlySpan<byte> data, long totalLength, string mediaType)
    {
        // totalLength is mixed into the hash to disambiguate same-prefix / different-length payloads,
        // so it must stay consistent with the bytes actually hashed. All current callers pass the full
        // buffer (totalLength == data.Length); assert it to catch a future short-buffer misuse early.
        Debug.Assert(totalLength == data.Length, $"Synthesize totalLength ({totalLength}) must match data.Length ({data.Length}).");

#pragma warning disable CA1850 // Static SHA256.HashData is .NET 5+ only; this project multi-targets netstandard2.0 / net472 where only ComputeHash exists.
        using SHA256 sha = SHA256.Create();
#pragma warning restore CA1850

        // Feed the payload in chunks to avoid allocating a full copy of the data.
        const int ChunkSize = 81920; // 80 KB — keeps temp buffers off the LOH.
        int offset = 0;
        while (offset < data.Length)
        {
            int count = Math.Min(ChunkSize, data.Length - offset);
            byte[] chunk = data.Slice(offset, count).ToArray();
            sha.TransformBlock(chunk, 0, count, null, 0);
            offset += count;
        }

        // Append totalLength as the final block to disambiguate same-prefix / different-length payloads.
        byte[] lengthBytes = BitConverter.GetBytes(totalLength);
        sha.TransformFinalBlock(lengthBytes, 0, lengthBytes.Length);
        byte[] hash = sha.Hash!;

        // First 6 bytes → 12 hex chars, lower-cased. 48 bits of prefix keeps the
        // birthday-collision probability negligible even for very large attachment counts.
        string prefix = ToLowerHex(hash, 6);
        return $"attachment-{prefix}.{ExtensionFor(mediaType)}";
    }

    private static string ToLowerHex(byte[] bytes, int count)
    {
        const string HexChars = "0123456789abcdef";
        char[] chars = new char[count * 2];
        for (int i = 0; i < count; i++)
        {
            chars[i * 2] = HexChars[(bytes[i] >> 4) & 0xF];
            chars[(i * 2) + 1] = HexChars[bytes[i] & 0xF];
        }

        return new string(chars);
    }

    private static string ExtensionFor(string mediaType) => mediaType.ToUpperInvariant() switch
    {
        // Documents and images
        "APPLICATION/PDF" => "pdf",
        "IMAGE/JPEG" => "jpg",
        "IMAGE/PNG" => "png",
        "IMAGE/TIFF" => "tiff",
        "IMAGE/BMP" => "bmp",
        "IMAGE/HEIF" => "heif",
        "IMAGE/HEIC" => "heic",
        "APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.WORDPROCESSINGML.DOCUMENT" => "docx",
        "APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.SPREADSHEETML.SHEET" => "xlsx",
        "APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.PRESENTATIONML.PRESENTATION" => "pptx",
        // Text
        "TEXT/PLAIN" => "txt",
        "TEXT/HTML" => "html",
        "TEXT/MARKDOWN" => "md",
        "TEXT/RTF" => "rtf",
        "TEXT/XML" => "xml",
        "APPLICATION/XML" => "xml",
        "MESSAGE/RFC822" => "eml",
        "APPLICATION/VND.MS-OUTLOOK" => "msg",
        // Audio
        "AUDIO/WAV" => "wav",
        "AUDIO/WAVE" => "wav",
        "AUDIO/X-WAV" => "wav",
        "AUDIO/MPEG" => "mp3",
        "AUDIO/MP3" => "mp3",
        "AUDIO/MP4" => "m4a",
        "AUDIO/M4A" => "m4a",
        "AUDIO/FLAC" => "flac",
        "AUDIO/OGG" => "ogg",
        "AUDIO/OPUS" => "opus",
        "AUDIO/WEBM" => "webm",
        "AUDIO/X-MS-WMA" => "wma",
        "AUDIO/AAC" => "aac",
        "AUDIO/AMR" => "amr",
        "AUDIO/3GPP" => "3gp",
        // Video
        "VIDEO/MP4" => "mp4",
        "VIDEO/QUICKTIME" => "mov",
        "VIDEO/X-MSVIDEO" => "avi",
        "VIDEO/WEBM" => "webm",
        "VIDEO/X-FLV" => "flv",
        "VIDEO/X-MS-WMV" => "wmv",
        "VIDEO/X-MS-ASF" => "asf",
        "VIDEO/X-MATROSKA" => "mkv",
        _ => "bin",
    };

    // MimeSniffer needs up to a full MPEG audio frame (plus a second sync word) to confirm MP3 via
    // double-sync, so the head window must be far larger than a bare magic number. This is a
    // zero-copy span slice over the already-in-memory payload, so widening it is essentially free.
    private static ReadOnlySpan<byte> SliceHead(ReadOnlySpan<byte> bytes)
        => bytes.Slice(0, Math.Min(bytes.Length, MimeSniffer.RecommendedHeadByteCount));
}
