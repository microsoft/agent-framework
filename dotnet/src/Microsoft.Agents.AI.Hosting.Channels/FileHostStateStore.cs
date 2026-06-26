// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// File-system-backed <see cref="IHostStateStore"/>. Persists reset-session aliases as one file per
/// isolation key and derives per-isolation-key workflow checkpoint directories.
/// </summary>
/// <remarks>
/// On construction it acquires an exclusive single-owner OS lock on its root directory: a second store over
/// the same directory (in this or another process) fails fast rather than corrupting shared state. Dispose
/// the store to release the lock.
/// </remarks>
public sealed class FileHostStateStore : IHostStateStore, IDisposable
{
    private readonly ConcurrentDictionary<string, string> _aliasCache = new(StringComparer.Ordinal);
    private readonly string _aliasesPath;
    private readonly string _checkpointsPath;
    private readonly object _gate = new();
    private readonly FileStream _lock;

    /// <summary>Initializes a new instance.</summary>
    public FileHostStateStore(HostStatePathOptions paths)
    {
        Throw.IfNull(paths);
        var root = paths.Root ?? "./.afhost";
        this._aliasesPath = paths.AliasesPath ?? Path.Combine(root, "aliases");
        this._checkpointsPath = paths.CheckpointsPath ?? Path.Combine(root, "checkpoints");
        Directory.CreateDirectory(root);
        Directory.CreateDirectory(this._aliasesPath);
        Directory.CreateDirectory(this._checkpointsPath);

        var lockPath = Path.Combine(root, ".lock");
        try
        {
            this._lock = new FileStream(lockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        }
        catch (IOException ex)
        {
            throw new InvalidOperationException(
                $"Another process already holds the hosting state lock at '{lockPath}'. Point each host at its own state directory.",
                ex);
        }
    }

    /// <inheritdoc />
    public ValueTask RotateSessionAliasAsync(string isolationKey, CancellationToken cancellationToken)
    {
        Throw.IfNullOrEmpty(isolationKey);
        var alias = Guid.NewGuid().ToString("N");
        this._aliasCache[isolationKey] = alias;
        lock (this._gate)
        {
            File.WriteAllText(this.AliasFile(isolationKey), alias);
        }
        return default;
    }

    /// <inheritdoc />
    public ValueTask<string?> GetActiveSessionAliasAsync(string isolationKey, CancellationToken cancellationToken)
    {
        Throw.IfNullOrEmpty(isolationKey);
        if (this._aliasCache.TryGetValue(isolationKey, out var cached))
        {
            return new(cached);
        }

        var file = this.AliasFile(isolationKey);
        string alias;
        lock (this._gate)
        {
            alias = File.Exists(file) ? File.ReadAllText(file) : isolationKey;
            if (!File.Exists(file))
            {
                File.WriteAllText(file, alias);
            }
        }
        this._aliasCache[isolationKey] = alias;
        return new(alias);
    }

    /// <inheritdoc />
    public ValueTask<string?> GetCheckpointLocationAsync(string isolationKey, CancellationToken cancellationToken)
    {
        ValidateIsolationKey(isolationKey);
        var dir = Path.Combine(this._checkpointsPath, EncodeFileName(isolationKey));
        Directory.CreateDirectory(dir);
        return new(dir);
    }

    /// <inheritdoc />
    public void Dispose() => this._lock.Dispose();

    private string AliasFile(string isolationKey) => Path.Combine(this._aliasesPath, EncodeFileName(isolationKey) + ".txt");

    private static string EncodeFileName(string raw) => Convert.ToHexString(System.Text.Encoding.UTF8.GetBytes(raw));

    /// <summary>
    /// Reject isolation keys that could escape the checkpoint root (CWE-22). Mirrors the Python host's
    /// denylist: no path separators or NUL, not dot-only, not absolute, no drive-letter prefix. Legitimate
    /// namespaced keys (e.g. <c>telegram:42</c>) are preserved.
    /// </summary>
    private static void ValidateIsolationKey(string isolationKey)
    {
        Throw.IfNullOrEmpty(isolationKey);

        var invalid =
            isolationKey.IndexOf('/') >= 0 ||
            isolationKey.IndexOf('\\') >= 0 ||
            isolationKey.IndexOf('\0') >= 0 ||
            isolationKey.Trim('.').Length == 0 ||
            Path.IsPathRooted(isolationKey) ||
            (isolationKey.Length >= 2 && char.IsLetter(isolationKey[0]) && isolationKey[1] == ':');

        if (invalid)
        {
            throw new ArgumentException($"Invalid isolation key for checkpoint path: '{isolationKey}'.", nameof(isolationKey));
        }
    }
}
