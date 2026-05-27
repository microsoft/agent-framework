// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Filesystem helpers for local CodeAct file mount management.
/// </summary>
internal static class FileMountHelper
{
    private const string WorkspaceMountPath = "/input";

    /// <summary>
    /// Normalize a display/capture mount path to a clean POSIX absolute path.
    /// </summary>
    public static string NormalizeMountPath(string mountPath)
    {
        var raw = mountPath.Trim().Replace("\\", "/");
        if (string.IsNullOrWhiteSpace(raw))
        {
            throw new ArgumentException("mount_path must not be empty.", nameof(mountPath));
        }

        var parts = raw.Split('/', StringSplitOptions.RemoveEmptyEntries)
            .Where(part => part != ".")
            .ToList();

        if (parts.Any(part => part == ".."))
        {
            throw new ArgumentException("mount_path must not contain '..' segments.", nameof(mountPath));
        }

        if (parts.Count == 0)
        {
            throw new ArgumentException("mount_path must point to a concrete absolute path.", nameof(mountPath));
        }

        return "/" + string.Join("/", parts);
    }

    /// <summary>
    /// Resolve a path and require it to point at an existing directory.
    /// </summary>
    public static DirectoryInfo ResolveExistingDirectory(string path)
    {
        var fullPath = Path.GetFullPath(path);
        var dir = new DirectoryInfo(fullPath);

        if (!dir.Exists)
        {
            throw new DirectoryNotFoundException($"Path '{path}' must point to an existing directory.");
        }

        return dir;
    }

    /// <summary>
    /// Normalize a public file-mount input.
    /// </summary>
    public static FileMount NormalizeFileMount(FileMount fileMount)
    {
        var hostPath = ResolveExistingDirectory(fileMount.HostPath);
        var mountPath = NormalizeMountPath(fileMount.MountPath ?? fileMount.HostPath);

        if (fileMount.WriteBytesLimit.HasValue && fileMount.WriteBytesLimit.Value < 0)
        {
            throw new ArgumentException("WriteBytesLimit must be non-negative or null.", nameof(fileMount));
        }

        return new FileMount(
            hostPath.FullName,
            mountPath,
            fileMount.Mode,
            fileMount.WriteBytesLimit
        );
    }

    /// <summary>
    /// Walk root recursively, yielding only real non-symlink files.
    /// </summary>
    private static IEnumerable<FileInfo> IterRealFiles(DirectoryInfo root)
    {
        var stack = new Stack<DirectoryInfo>();
        stack.Push(root);

        while (stack.Count > 0)
        {
            var current = stack.Pop();
            IEnumerable<FileSystemInfo> entries;

            try
            {
                entries = current.EnumerateFileSystemInfos();
            }
            catch (IOException)
            {
                continue;
            }
            catch (UnauthorizedAccessException)
            {
                continue;
            }

            foreach (var entry in entries)
            {
                try
                {
                    // Skip symlinks
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
                catch (IOException)
                {
                    continue;
                }
                catch (UnauthorizedAccessException)
                {
                    continue;
                }
            }
        }
    }

    /// <summary>
    /// Capture (size, mtime_ns) for real files under read-write mounts.
    /// </summary>
    public static Dictionary<string, Dictionary<string, (long size, long mtimeNs)>> SnapshotWritableMounts(
        IEnumerable<FileMount> mounts)
    {
        var snapshot = new Dictionary<string, Dictionary<string, (long size, long mtimeNs)>>();

        foreach (var mount in mounts)
        {
            if (mount.Mode != FileMountMode.ReadWrite)
            {
                continue;
            }

            var hostRoot = new DirectoryInfo(mount.HostPath);
            var perMount = new Dictionary<string, (long size, long mtimeNs)>();

            foreach (var entry in IterRealFiles(hostRoot))
            {
                try
                {
                    var relativePath = Path.GetRelativePath(hostRoot.FullName, entry.FullName)
                        .Replace(Path.DirectorySeparatorChar, '/');

                    // Convert to ticks (100-nanosecond intervals since 1/1/0001)
                    // Python uses nanoseconds since epoch, we'll use ticks as a proxy
                    var mtimeNs = entry.LastWriteTimeUtc.Ticks;

                    perMount[relativePath] = (entry.Length, mtimeNs);
                }
                catch (IOException)
                {
                    continue;
                }
                catch (UnauthorizedAccessException)
                {
                    continue;
                }
            }

            snapshot[mount.MountPath] = perMount;
        }

        return snapshot;
    }

    /// <summary>
    /// Return content items for files written under read-write mounts.
    /// </summary>
    public static List<AIContent> CaptureWrittenFiles(
        IEnumerable<FileMount> mounts,
        Dictionary<string, Dictionary<string, (long size, long mtimeNs)>> preState,
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

            var hostRoot = new DirectoryInfo(mount.HostPath);
            var before = preState.TryGetValue(mount.MountPath, out var beforeDict)
                ? beforeDict
                : new Dictionary<string, (long size, long mtimeNs)>();

            long mountBytes = 0;

            foreach (var entry in IterRealFiles(hostRoot).OrderBy(f => f.FullName))
            {
                try
                {
                    var relativePath = Path.GetRelativePath(hostRoot.FullName, entry.FullName)
                        .Replace(Path.DirectorySeparatorChar, '/');

                    var mtimeNs = entry.LastWriteTimeUtc.Ticks;
                    var current = (entry.Length, mtimeNs);

                    // Skip if file hasn't changed
                    if (before.TryGetValue(relativePath, out var previous) && previous == current)
                    {
                        continue;
                    }

                    var sandboxPath = $"{mount.MountPath.TrimEnd('/')}/{relativePath}";

                    // Check file size limit
                    if (entry.Length > limits.MaxCapturedFileBytes)
                    {
                        captured.Add(new TextContent($"[file {sandboxPath} omitted: file exceeds capture limit]"));
                        continue;
                    }

                    // Check mount-specific limit
                    if (mount.WriteBytesLimit.HasValue && mountBytes + entry.Length > mount.WriteBytesLimit.Value)
                    {
                        captured.Add(new TextContent($"[file {sandboxPath} omitted: mount capture limit exceeded]"));
                        continue;
                    }

                    // Check total capture limit
                    if (totalBytes + entry.Length > limits.MaxTotalCapturedFileBytes)
                    {
                        captured.Add(new TextContent($"[file {sandboxPath} omitted: total capture limit exceeded]"));
                        continue;
                    }

                    // Read and capture the file
                    var data = File.ReadAllBytes(entry.FullName);
                    var mediaType = GetMediaType(entry.Name);

                    captured.Add(new DataContent(data, mediaType)
                    {
                        AdditionalProperties = new Dictionary<string, object?>
                        {
                            ["path"] = sandboxPath
                        }
                    });

                    mountBytes += entry.Length;
                    totalBytes += entry.Length;
                }
                catch (IOException)
                {
                    continue;
                }
                catch (UnauthorizedAccessException)
                {
                    continue;
                }
            }
        }

        return captured;
    }

    /// <summary>
    /// Get media type for a file based on its extension.
    /// </summary>
    private static string GetMediaType(string fileName)
    {
        var extension = Path.GetExtension(fileName).ToLowerInvariant();

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
            _ => "application/octet-stream"
        };
    }
}
