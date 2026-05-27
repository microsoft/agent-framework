// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
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
/// → synthesized <c>attachment-{sha256[0..6]}.{ext}</c>. Supported media types cover documents,
/// images, text, audio, and video per the Azure CU input file limits:
/// https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits.
/// </remarks>
internal static class AttachmentDetector
{
    private const string OctetStream = "application/octet-stream";

    // Allow-list of supported media types. Comparisons are case-insensitive (OrdinalIgnoreCase).
    // audio/wave and audio/x-wav are accepted as WAV aliases up front for maximum tolerance of
    // HTTP-server-supplied types.
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
            // Unknown / unsupported → silently skip; must never block the agent run.
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

        return Synthesize(bytes, mediaType);
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

        // Fall back to the URI's last segment when it looks like a real filename.
        string? last = uc.Uri.Segments.Length > 0 ? uc.Uri.Segments[uc.Uri.Segments.Length - 1] : null;
        last = last?.Trim('/');
        if (!string.IsNullOrEmpty(last) && last!.Contains('.'))
        {
            string cleaned = SanitizeFilename(last);
            if (!string.IsNullOrEmpty(cleaned))
            {
                return cleaned;
            }
        }

        // Synthesize from a hash of the URI string when no real filename can be derived.
        byte[] uriBytes = Encoding.UTF8.GetBytes(uc.Uri.ToString());
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

    private static readonly char[] SpaceSplit = [' '];

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

        string[] tokens = sb.ToString().Split(SpaceSplit, StringSplitOptions.RemoveEmptyEntries);
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

    private static string Synthesize(byte[] bytes, string mediaType)
    {
#pragma warning disable CA1850 // Static SHA256.HashData is .NET 5+ only; this project multi-targets netstandard2.0 / net472 where only ComputeHash exists.
        using SHA256 sha = SHA256.Create();
        byte[] hash = sha.ComputeHash(bytes);
#pragma warning restore CA1850

        // First 3 bytes → 6 hex chars, lower-cased.
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
