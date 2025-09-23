// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides a file system-based implementation of a JSON checkpoint store that persists checkpoint data and index
/// information to disk using JSON files.
/// </summary>
/// <remarks>This class manages checkpoint storage by writing JSON files to a specified directory and maintaining
/// an index file for efficient retrieval. It is intended for scenarios where durable, process-exclusive checkpoint
/// persistence is required. Instances of this class are not thread-safe and should not be shared across multiple
/// threads without external synchronization. The class implements IDisposable; callers should ensure Dispose is called
/// to release file handles and system resources when the store is no longer needed.</remarks>
public sealed class FileSystemJsonCheckpointStore : JsonCheckpointStore, IDisposable
{
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Usage", "CA2213:Disposable fields should be disposed",
        Justification = "It is disposed, the analyzer is just not picking it up properly")]
    private FileStream? _indexFile;

    internal DirectoryInfo Directory { get; }
    internal HashSet<CheckpointInfo> CheckpointIndex { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="FileSystemJsonCheckpointStore"/> class that uses the specified directory
    /// </summary>
    /// <param name="directory"></param>
    /// <exception cref="ArgumentNullException"></exception>
    /// <exception cref="InvalidOperationException"></exception>
    public FileSystemJsonCheckpointStore(DirectoryInfo directory)
    {
        this.Directory = directory ?? throw new ArgumentNullException(nameof(directory));

        if (!directory.Exists)
        {
            directory.Create();
        }

        try
        {
            this._indexFile = File.Open(Path.Combine(directory.FullName, "index.jsonl"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        }
        catch
        {
            throw new InvalidOperationException($"The store at '{directory.FullName}' is already in use by another process.");
        }

        try
        {
            // read the lines of indexfile and parse them as CheckpointInfos
            this.CheckpointIndex = [];
            using StreamReader reader = new(this._indexFile, encoding: Encoding.UTF8, detectEncodingFromByteOrderMarks: false, bufferSize: -1, leaveOpen: true);
            while (reader.ReadLine() is string line)
            {
                if (JsonSerializer.Deserialize(line, KeyTypeInfo) is { } info)
                {
                    this.CheckpointIndex.Add(info);
                }
            }
        }
        catch
        {
            throw new InvalidOperationException($"Could not load store at '{directory.FullName}'. Index corrupted.");
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        FileStream? indexFileLocal = Interlocked.Exchange(ref this._indexFile, null);
        indexFileLocal?.Dispose();
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
        Justification = "Throw helper does not exist in NetFx 4.7.2")]
    private void CheckDisposed()
    {
        if (this._indexFile is null)
        {
            throw new ObjectDisposedException($"{nameof(FileSystemJsonCheckpointStore)}({this.Directory.FullName})");
        }
    }

    private string GetFileNameForCheckpoint(string runId, CheckpointInfo key)
        => Path.Combine(this.Directory.FullName, $"{runId}_{key.CheckpointId}.json");

    private CheckpointInfo GetUnusedCheckpointInfo(string runId)
    {
        CheckpointInfo key;
        do
        {
            key = new(runId);
        } while (!this.CheckpointIndex.Add(key));

        return key;
    }

    /// <inheritdoc/>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1835:Prefer the 'Memory'-based overloads for 'ReadAsync' and 'WriteAsync'",
        Justification = "Memory-based overload is missing for 4.7.2")]
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string runId, JsonElement value, CheckpointInfo? parent = null)
    {
        this.CheckDisposed();

        CheckpointInfo key = this.GetUnusedCheckpointInfo(runId);
        string fileName = this.GetFileNameForCheckpoint(runId, key);
        try
        {
            using Stream checkpointStream = File.Open(fileName, FileMode.Create, FileAccess.Write, FileShare.None);
            using Utf8JsonWriter jsonWriter = new(checkpointStream, new JsonWriterOptions() { Indented = false });
            value.WriteTo(jsonWriter);

            JsonSerializer.Serialize(this._indexFile!, key, KeyTypeInfo);
            byte[] bytes = Encoding.UTF8.GetBytes(Environment.NewLine);
            await this._indexFile!.WriteAsync(bytes, 0, bytes.Length, CancellationToken.None).ConfigureAwait(false);

            return key;
        }
        catch (Exception ex)
        {
            this.CheckpointIndex.Remove(key);

            try
            {
                // try to clean up after ourselves
                File.Delete(fileName);
            }
            catch { }

            throw new InvalidOperationException($"Could not create checkpoint in store at '{this.Directory.FullName}'.", ex);
        }
    }

    /// <inheritdoc/>
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string runId, CheckpointInfo key)
    {
        this.CheckDisposed();
        string fileName = this.GetFileNameForCheckpoint(runId, key);

        if (!this.CheckpointIndex.Contains(key) ||
            !File.Exists(fileName))
        {
            throw new KeyNotFoundException($"Checkpoint '{key.CheckpointId}' not found in store at '{this.Directory.FullName}'.");
        }

        using FileStream checkpointFileStream = File.Open(fileName, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = await JsonDocument.ParseAsync(checkpointFileStream).ConfigureAwait(false);

        return document.RootElement.Clone();
    }

    /// <inheritdoc/>
    public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string runId, CheckpointInfo? withParent = null)
    {
        this.CheckDisposed();

        return new(this.CheckpointIndex);
    }
}
