// Copyright (c) Microsoft. All rights reserved.

using System.Security.Cryptography;
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
/// Mirrors Python <c>_detection.detect_and_strip_files</c>. Unsupported content silently
/// skips (must never block the agent run). Filename resolution order (per dev plan task 3.2):
/// <see cref="DataContent.Name"/> → <see cref="AIContent.AdditionalProperties"/>["filename"] →
/// synthesized <c>attachment-{sha256[0..6]}.{ext}</c>. Supported media types match the Python
/// provider's <c>SUPPORTED_MEDIA_TYPES</c> set (documents, images, text, audio, video) per the
/// Azure CU input file limits: https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits.
/// </remarks>
internal static class AttachmentDetector
{
    private const string OctetStream = "application/octet-stream";

    // Match Python's SUPPORTED_MEDIA_TYPES (agent_framework_azure_contentunderstanding._detection).
    // Comparisons are case-insensitive (StringComparer.OrdinalIgnoreCase). audio/wave and
    // audio/x-wav are accepted as WAV aliases — Python normalizes them via MIME_ALIASES during
    // sniffing; we accept them up front for maximum tolerance of HTTP-server-supplied types.
    private static readonly HashSet<string> SupportedMediaTypes = new(StringComparer.OrdinalIgnoreCase)
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
        byte[] bytes = dc.Data.ToArray();
        string? sniffed = bytes.Length > 0 ? MimeSniffer.Detect(SliceHead(bytes)) : null;
        string supplied = dc.MediaType ?? string.Empty;

        // Treat octet-stream as "unknown — fall back to sniff".
        string resolved = string.Equals(supplied, OctetStream, StringComparison.OrdinalIgnoreCase)
            ? (sniffed ?? string.Empty)
            : (!string.IsNullOrEmpty(supplied) ? supplied : sniffed ?? string.Empty);

        if (!SupportedMediaTypes.Contains(resolved))
        {
            // Unknown / unsupported → silently skip per parity with Python.
            return null;
        }

        string filename = ResolveDataFilename(dc, resolved, bytes);
        return new DetectedAttachment(dc, resolved, filename, bytes, null);
    }

    private static DetectedAttachment? TryDetectUri(UriContent uc)
    {
        string resolved = uc.MediaType ?? string.Empty;
        if (!SupportedMediaTypes.Contains(resolved))
        {
            return null;
        }

        string filename = ResolveUriFilename(uc, resolved);
        return new DetectedAttachment(uc, resolved, filename, null, uc.Uri);
    }

    private static string ResolveDataFilename(DataContent dc, string mediaType, byte[] bytes)
    {
        if (!string.IsNullOrEmpty(dc.Name))
        {
            return dc.Name!;
        }

        string? fromProps = TryGetFilenameFromProperties(dc.AdditionalProperties);
        if (!string.IsNullOrEmpty(fromProps))
        {
            return fromProps!;
        }

        return Synthesize(bytes, mediaType);
    }

    private static string ResolveUriFilename(UriContent uc, string mediaType)
    {
        string? fromProps = TryGetFilenameFromProperties(uc.AdditionalProperties);
        if (!string.IsNullOrEmpty(fromProps))
        {
            return fromProps!;
        }

        // Fall back to the URI's last segment when it looks like a real filename.
        string? last = uc.Uri.Segments.Length > 0 ? uc.Uri.Segments[uc.Uri.Segments.Length - 1] : null;
        last = last?.Trim('/');
        if (!string.IsNullOrEmpty(last) && last!.Contains('.'))
        {
            return last;
        }

        // Synthesize from a hash of the URI string when no real filename can be derived.
        byte[] uriBytes = System.Text.Encoding.UTF8.GetBytes(uc.Uri.ToString());
        return Synthesize(uriBytes, mediaType);
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

    private static string Synthesize(byte[] bytes, string mediaType)
    {
#pragma warning disable CA1850 // Static SHA256.HashData is .NET 5+ only; this project multi-targets netstandard2.0 / net472 where only ComputeHash exists.
        using SHA256 sha = SHA256.Create();
        byte[] hash = sha.ComputeHash(bytes);
#pragma warning restore CA1850

        // First 3 bytes → 6 hex chars, lower-cased to match Python's behavior.
        string prefix = ToLowerHex(hash, 3);
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

    private static ReadOnlySpan<byte> SliceHead(byte[] bytes)
        => bytes.AsSpan(0, Math.Min(bytes.Length, 64));
}
