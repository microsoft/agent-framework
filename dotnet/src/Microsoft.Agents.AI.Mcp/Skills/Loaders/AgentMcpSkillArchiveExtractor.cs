// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.IO;
using System.IO.Compression;

namespace Microsoft.Agents.AI;

/// <summary>
/// Unpacks skill archives downloaded from an MCP server into a local directory.
/// </summary>
/// <remarks>
/// Supports ZIP payloads. Extraction is guarded against path-traversal ("zip-slip") attacks and
/// bounded by a maximum file count and total uncompressed size to mitigate decompression-bomb attacks.
/// </remarks>
internal static class AgentMcpSkillArchiveExtractor
{
    /// <summary>
    /// The default maximum number of files that may be extracted from a single archive, sized for a
    /// typical well-formed skill (a handful of files) with headroom over the observed average.
    /// </summary>
    internal const int DefaultMaxFileCount = 20;

    /// <summary>
    /// The default maximum total uncompressed size, in bytes, of all files extracted from a single
    /// archive, sized for a typical well-formed skill (well under ~1 MB).
    /// </summary>
    internal const long DefaultMaxUncompressedSizeBytes = 1L * 1024 * 1024;

    private const int CopyBufferSize = 81920;

    /// <summary>
    /// Determines the archive format from the advertised media type, the source URL, and the leading
    /// bytes of the payload (magic-number sniffing takes precedence as it is the most reliable).
    /// </summary>
    /// <param name="bytes">The archive bytes.</param>
    /// <param name="mediaType">The advertised MIME type, if any.</param>
    /// <param name="url">The resource URL the archive was read from, if any.</param>
    /// <returns>The detected <see cref="ArchiveFormat"/>, or <see cref="ArchiveFormat.Unknown"/>.</returns>
    internal static ArchiveFormat DetectFormat(byte[] bytes, string? mediaType, string? url)
    {
        // Magic-number sniffing is the most reliable signal.
        // Reject gzip by signature before considering potentially incorrect MIME type or URL hints.
        if (bytes.Length >= 2 && bytes[0] == 0x1F && bytes[1] == 0x8B)
        {
            return ArchiveFormat.Unknown;
        }

        if (bytes.Length >= 4 && bytes[0] == 0x50 && bytes[1] == 0x4B &&
            (bytes[2] == 0x03 || bytes[2] == 0x05 || bytes[2] == 0x07))
        {
            return ArchiveFormat.Zip;
        }

        string media = mediaType?.Trim() ?? string.Empty;
        if (string.Equals(media, "application/zip", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(media, "application/x-zip-compressed", StringComparison.OrdinalIgnoreCase))
        {
            return ArchiveFormat.Zip;
        }

        string u = url ?? string.Empty;
        if (u.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
        {
            return ArchiveFormat.Zip;
        }

        return ArchiveFormat.Unknown;
    }

    /// <summary>
    /// Extracts the supplied archive into <paramref name="targetDirectory"/>.
    /// </summary>
    /// <param name="bytes">The archive bytes.</param>
    /// <param name="format">The archive container format.</param>
    /// <param name="targetDirectory">The directory the archive is unpacked into. Created if missing.</param>
    /// <param name="maxFileCount">The maximum number of files that may be extracted from the archive.</param>
    /// <param name="maxUncompressedSizeBytes">The maximum total uncompressed size, in bytes, of all extracted files.</param>
    /// <exception cref="NotSupportedException">The format is not <see cref="ArchiveFormat.Zip"/>.</exception>
    /// <exception cref="InvalidDataException">The archive exceeds one of the supplied limits.</exception>
    internal static void Extract(
        byte[] bytes,
        ArchiveFormat format,
        string targetDirectory,
        int? maxFileCount = null,
        long? maxUncompressedSizeBytes = null)
    {
        maxFileCount ??= DefaultMaxFileCount;
        maxUncompressedSizeBytes ??= DefaultMaxUncompressedSizeBytes;

        if (format != ArchiveFormat.Zip)
        {
            throw new NotSupportedException($"Unsupported skill archive format '{format}'. Use ZIP instead.");
        }

        Directory.CreateDirectory(targetDirectory);
        string fullTarget = Path.GetFullPath(targetDirectory);

        using var source = new MemoryStream(bytes, writable: false);
        ExtractZip(source, fullTarget, maxFileCount.Value, maxUncompressedSizeBytes.Value);
    }

    private static void ExtractZip(Stream source, string fullTarget, int maxFileCount, long maxUncompressedSizeBytes)
    {
        using var archive = new ZipArchive(source, ZipArchiveMode.Read, leaveOpen: true);

        long remainingBytes = maxUncompressedSizeBytes;
        int fileCount = 0;

        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            // Directory entries have an empty Name.
            if (entry.Name.Length == 0)
            {
                continue;
            }

            if (++fileCount > maxFileCount)
            {
                throw new InvalidDataException($"Skill archive exceeds the maximum allowed file count ({maxFileCount}).");
            }

            string? destination = ResolveDestination(fullTarget, entry.FullName); // CodeQL [SM02729] ResolveDestination rejects paths outside fullTarget.
            if (destination is null)
            {
                continue;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);

            using Stream entryStream = entry.Open();
            using FileStream output = File.Create(destination);
            CopyWithLimit(entryStream, output, ref remainingBytes);
        }
    }

    /// <summary>
    /// Copies <paramref name="source"/> to <paramref name="destination"/> while decrementing a shared
    /// uncompressed-byte budget, throwing once it is exhausted. This is the authoritative defense against
    /// decompression bombs because it counts bytes actually produced by the decompressor rather than
    /// trusting archive metadata which may be inaccurate. Peak memory is bounded to a single buffer.
    /// </summary>
    /// <exception cref="InvalidDataException">The remaining byte budget is exceeded.</exception>
    private static void CopyWithLimit(Stream source, Stream destination, ref long remainingBytes)
    {
        byte[] buffer = ArrayPool<byte>.Shared.Rent(CopyBufferSize);
        try
        {
            int read;
            while ((read = source.Read(buffer, 0, buffer.Length)) > 0)
            {
                remainingBytes -= read;
                if (remainingBytes < 0)
                {
                    throw new InvalidDataException("Skill archive exceeds the maximum allowed uncompressed size.");
                }

                destination.Write(buffer, 0, read);
            }
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }

    /// <summary>
    /// Resolves an archive entry path to an absolute destination beneath <paramref name="fullTarget"/>,
    /// or <see langword="null"/> when the entry would escape the target directory (zip-slip).
    /// </summary>
    private static string? ResolveDestination(string fullTarget, string entryPath)
    {
        if (string.IsNullOrWhiteSpace(entryPath))
        {
            return null;
        }

        // Normalize separators and reject absolute / rooted entry paths outright.
        string normalized = entryPath.Replace('\\', '/').TrimStart('/');
        if (normalized.Length == 0 || Path.IsPathRooted(normalized))
        {
            return null;
        }

        string destination = Path.GetFullPath(Path.Combine(fullTarget, normalized));
        if (!IsPathContainedIn(fullTarget, destination))
        {
            return null;
        }

        return destination;
    }

    /// <summary>
    /// Returns <see langword="true"/> when <paramref name="candidatePath"/> resolves to a location
    /// beneath <paramref name="parentDirectory"/>.
    /// </summary>
    internal static bool IsPathContainedIn(string parentDirectory, string candidatePath)
    {
        string fullParent = Path.GetFullPath(parentDirectory);
        string fullCandidate = Path.GetFullPath(candidatePath);

        // Append a trailing separator so the containment check doesn't false-match sibling
        // directories. e.g. "/skills/myskill" matches "/skills/myskill-evil/", but
        // "/skills/myskill/" does not.
        string prefix = fullParent.EndsWith(Path.DirectorySeparatorChar.ToString(), StringComparison.Ordinal)
            ? fullParent
            : fullParent + Path.DirectorySeparatorChar;

        return fullCandidate.StartsWith(
            prefix,
            OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
    }
}
