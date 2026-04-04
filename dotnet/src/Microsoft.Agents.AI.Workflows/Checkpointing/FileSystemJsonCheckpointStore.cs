// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

internal record CheckpointFileIndexEntry(CheckpointInfo CheckpointInfo, string FileName);

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

    private static JsonTypeInfo<CheckpointFileIndexEntry> EntryTypeInfo => WorkflowsJsonUtilities.JsonContext.Default.CheckpointFileIndexEntry;

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
#if NET
            const int BufferSize = -1;
#else
            const int BufferSize = 1024;
#endif
            using StreamReader reader = new(this._indexFile, encoding: Encoding.UTF8, detectEncodingFromByteOrderMarks: false, BufferSize, leaveOpen: true);
            while (reader.ReadLine() is string line)
            {
                if (JsonSerializer.Deserialize(line, EntryTypeInfo) is { } entry)
                {
                    // We never actually use the file names from the index entries since they can be derived from the CheckpointInfo, but it is useful to
                    // have the UrlEncoded file names in the index file for human readability
                    this.CheckpointIndex.Add(entry.CheckpointInfo);
                }
            }
        }
        catch (Exception exception)
        {
            throw new InvalidOperationException($"Could not load store at '{directory.FullName}'. Index corrupted.", exception);
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

    internal string GetFileNameForCheckpoint(string sessionId, CheckpointInfo key)
    {
        string protoPath = $"{sessionId}_{key.CheckpointId}.json";

        // Escape the protoPath to ensure it is a valid file name, especially if sessionId or CheckpointId contain path separators, etc.
        return Uri.EscapeDataString(protoPath) // This takes care of most of the invalid path characters
                  .Replace(".", "%2E");        // This takes care of escaping the root folder, since EscapeDataString does not escape dots
    }

    private CheckpointInfo GetUnusedCheckpointInfo(string sessionId)
    {
        CheckpointInfo key;
        do
        {
            key = new(sessionId);
        } while (!this.CheckpointIndex.Add(key));

        return key;
    }

    /// <inheritdoc/>
    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1835:Prefer the 'Memory'-based overloads for 'ReadAsync' and 'WriteAsync'",
        Justification = "Memory-based overload is missing for 4.7.2")]
    public override async ValueTask<CheckpointInfo> CreateCheckpointAsync(string sessionId, JsonElement value, CheckpointInfo? parent = null)
    {
        this.CheckDisposed();

        CheckpointInfo key = this.GetUnusedCheckpointInfo(sessionId);
        string fileName = this.GetFileNameForCheckpoint(sessionId, key);
        string filePath = Path.Combine(this.Directory.FullName, fileName);

        try
        {
            using Stream checkpointStream = File.Open(filePath, FileMode.Create, FileAccess.Write, FileShare.None);
            using Utf8JsonWriter jsonWriter = new(checkpointStream, new JsonWriterOptions() { Indented = false });
            value.WriteTo(jsonWriter);

            CheckpointFileIndexEntry entry = new(key, fileName);
            JsonSerializer.Serialize(this._indexFile!, entry, EntryTypeInfo);
            byte[] bytes = Encoding.UTF8.GetBytes(Environment.NewLine);
            await this._indexFile!.WriteAsync(bytes, 0, bytes.Length, CancellationToken.None).ConfigureAwait(false);
            await this._indexFile!.FlushAsync(CancellationToken.None).ConfigureAwait(false);

            return key;
        }
        catch (Exception ex)
        {
            this.CheckpointIndex.Remove(key);

            try
            {
                // try to clean up after ourselves
                File.Delete(filePath);
            }
            catch { }

            throw new InvalidOperationException($"Could not create checkpoint in store at '{this.Directory.FullName}'.", ex);
        }
    }

    /// <inheritdoc/>
    public override async ValueTask<JsonElement> RetrieveCheckpointAsync(string sessionId, CheckpointInfo key)
    {
        this.CheckDisposed();
        string fileName = this.GetFileNameForCheckpoint(sessionId, key);
        string filePath = Path.Combine(this.Directory.FullName, fileName);

        if (!this.CheckpointIndex.Contains(key) ||
            !File.Exists(fileName))
        {
            throw new KeyNotFoundException($"Checkpoint '{key.CheckpointId}' not found in store at '{this.Directory.FullName}'.");
        }

        using FileStream checkpointFileStream = File.Open(filePath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using JsonDocument document = await JsonDocument.ParseAsync(checkpointFileStream).ConfigureAwait(false);

        return document.RootElement.Clone();
    }

    /// <inheritdoc/>
    public override ValueTask<IEnumerable<CheckpointInfo>> RetrieveIndexAsync(string sessionId, CheckpointInfo? withParent = null)
    {
        this.CheckDisposed();

        return new(this.CheckpointIndex);
    }
}
