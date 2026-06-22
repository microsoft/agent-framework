// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Filesystem helpers for read-write mount snapshotting and capture.
/// </summary>
internal static class FileMountHelper
{
    /// <summary>Normalizes and validates a mount path (must be a clean absolute POSIX-style path).</summary>
    public static string NormalizeMountPath(string mountPath)
    {
        if (string.IsNullOrWhiteSpace(mountPath))
        {
            throw new ArgumentException("Mount path must not be empty.", nameof(mountPath));
        }

        var raw = mountPath.Trim().Replace('\\', '/');
        var parts = raw.Split('/', StringSplitOptions.RemoveEmptyEntries)
            .Where(p => p != ".")
            .ToList();

        if (parts.Any(p => p == ".."))
        {
            throw new ArgumentException("Mount path must not contain '..' segments.", nameof(mountPath));
        }

        if (parts.Count == 0)
        {
            throw new ArgumentException("Mount path must point to a concrete absolute path.", nameof(mountPath));
        }

        return "/" + string.Join("/", parts);
    }

    /// <summary>
    /// Validates a FileMount and returns a normalized copy (resolved host path, normalized mount path).
    /// </summary>
    public static FileMount Normalize(FileMount mount)
    {
        if (mount is null)
        {
            throw new ArgumentNullException(nameof(mount));
        }

        if (string.IsNullOrWhiteSpace(mount.HostPath))
        {
            throw new ArgumentException("HostPath must not be empty.", nameof(mount));
        }

        var fullHost = Path.GetFullPath(mount.HostPath);
        if (!Directory.Exists(fullHost) && !File.Exists(fullHost))
        {
            throw new DirectoryNotFoundException($"FileMount host path '{mount.HostPath}' does not exist.");
        }

        if (mount.WriteBytesLimit.HasValue && mount.WriteBytesLimit.Value < 0)
        {
            throw new ArgumentException("WriteBytesLimit must be non-negative when set.", nameof(mount));
        }

        return new FileMount(fullHost, NormalizeMountPath(mount.MountPath), mount.Mode, mount.WriteBytesLimit);
    }

    /// <summary>Snapshot of (size, last-write-time ticks) per relative path under a writable mount.</summary>
    public sealed class MountSnapshot
    {
        public MountSnapshot(IReadOnlyDictionary<string, (long Size, long Ticks)> files)
        {
            this.Files = files;
        }

        public IReadOnlyDictionary<string, (long Size, long Ticks)> Files { get; }
    }

    /// <summary>Captures the current file inventory of read-write mounts before execution.</summary>
    public static Dictionary<string, MountSnapshot> SnapshotWritableMounts(IReadOnlyList<FileMount> mounts)
    {
        var snapshot = new Dictionary<string, MountSnapshot>(StringComparer.Ordinal);

        foreach (var mount in mounts)
        {
            if (mount.Mode != FileMountMode.ReadWrite)
            {
                continue;
            }

            var root = new DirectoryInfo(mount.HostPath);
            if (!root.Exists)
            {
                snapshot[mount.MountPath] = new MountSnapshot(new Dictionary<string, (long, long)>());
                continue;
            }

            var files = new Dictionary<string, (long Size, long Ticks)>(StringComparer.Ordinal);
            foreach (var file in EnumerateRealFiles(root))
            {
                var rel = MakeRelative(root.FullName, file.FullName);
                files[rel] = (file.Length, file.LastWriteTimeUtc.Ticks);
            }

            snapshot[mount.MountPath] = new MountSnapshot(files);
        }

        return snapshot;
    }

    /// <summary>Captures files that were created or modified in read-write mounts since the snapshot was taken.</summary>
    public static List<AIContent> CaptureWrittenFiles(
        IReadOnlyList<FileMount> mounts,
        IReadOnlyDictionary<string, MountSnapshot> preState,
        ProcessExecutionLimits limits)
    {
        var captured = new List<AIContent>();
        long totalBytes = 0;

        foreach (var mount in mounts)
        {
            if (mount.Mode != FileMountMode.ReadWrite)
            {
                continue;
            }

            var root = new DirectoryInfo(mount.HostPath);
            if (!root.Exists)
            {
                continue;
            }

            preState.TryGetValue(mount.MountPath, out var before);
            var beforeFiles = before?.Files ?? new Dictionary<string, (long, long)>();
            long mountBytes = 0;
            var perMountLimit = mount.WriteBytesLimit ?? limits.MaxCapturedFileBytes;

            foreach (var file in EnumerateRealFiles(root).OrderBy(f => f.FullName, StringComparer.Ordinal))
            {
                var rel = MakeRelative(root.FullName, file.FullName);
                var current = (file.Length, file.LastWriteTimeUtc.Ticks);

                if (beforeFiles.TryGetValue(rel, out var previous) && previous == current)
                {
                    continue;
                }

                var sandboxPath = mount.MountPath.TrimEnd('/') + "/" + rel;

                if (file.Length > limits.MaxCapturedFileBytes)
                {
                    captured.Add(new TextContent($"[file {sandboxPath} omitted: exceeds per-file capture limit]"));
                    continue;
                }

                if (mountBytes + file.Length > perMountLimit)
                {
                    captured.Add(new TextContent($"[file {sandboxPath} omitted: per-mount capture limit reached]"));
                    continue;
                }

                if (totalBytes + file.Length > limits.MaxTotalCapturedFileBytes)
                {
                    captured.Add(new TextContent($"[file {sandboxPath} omitted: total capture limit reached]"));
                    continue;
                }

                byte[] data;
                try
                {
                    data = File.ReadAllBytes(file.FullName);
                }
                catch (IOException)
                {
                    continue;
                }
                catch (UnauthorizedAccessException)
                {
                    continue;
                }

                captured.Add(new DataContent(data, GuessMediaType(file.Name))
                {
                    AdditionalProperties = new AdditionalPropertiesDictionary
                    {
                        ["path"] = sandboxPath,
                    },
                });

                mountBytes += file.Length;
                totalBytes += file.Length;
            }
        }

        return captured;
    }

    private static string MakeRelative(string root, string full)
    {
        var rel = Path.GetRelativePath(root, full);
        return rel.Replace(Path.DirectorySeparatorChar, '/');
    }

    private static IEnumerable<FileInfo> EnumerateRealFiles(DirectoryInfo root)
    {
        var stack = new Stack<DirectoryInfo>();
        stack.Push(root);

        while (stack.Count > 0)
        {
            var current = stack.Pop();
            FileSystemInfo[] entries;
            try
            {
                entries = current.GetFileSystemInfos();
            }
            catch (IOException)
            {
                continue;
            }

            foreach (var entry in entries)
            {
                if (entry.Attributes.HasFlag(FileAttributes.ReparsePoint))
                {
                    continue;
                }

                if (entry is DirectoryInfo dir)
                {
                    stack.Push(dir);
                }
                else if (entry is FileInfo file)
                {
                    yield return file;
                }
            }
        }
    }

    private static string GuessMediaType(string fileName)
    {
#pragma warning disable CA1308 // Normalize strings to uppercase - file extensions are conventionally lowercase
        var extension = Path.GetExtension(fileName).ToLowerInvariant();
#pragma warning restore CA1308
        return extension switch
        {
            ".txt" => "text/plain",
            ".json" => "application/json",
            ".xml" => "application/xml",
            ".html" => "text/html",
            ".css" => "text/css",
            ".js" => "application/javascript",
            ".png" => "image/png",
            ".jpg" or ".jpeg" => "image/jpeg",
            ".gif" => "image/gif",
            ".svg" => "image/svg+xml",
            ".pdf" => "application/pdf",
            ".zip" => "application/zip",
            ".csv" => "text/csv",
            ".md" => "text/markdown",
            ".py" => "text/x-python",
            ".cs" => "text/x-csharp",
            _ => "application/octet-stream",
        };
    }
}
