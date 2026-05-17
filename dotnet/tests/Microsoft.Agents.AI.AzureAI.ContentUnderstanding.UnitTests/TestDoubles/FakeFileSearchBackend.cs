// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding.UnitTests;

/// <summary>
/// Fake <see cref="FileSearchBackend"/> for Phase 9 tests. Records every upload + delete call,
/// optionally simulates timeouts or hard failures, and hands out incrementing fake file ids.
/// </summary>
internal sealed class FakeFileSearchBackend : FileSearchBackend
{
    private int _fileIdCounter;

    public ConcurrentBag<UploadCall> UploadCalls { get; } = new();

    public ConcurrentBag<string> DeleteCalls { get; } = new();

    /// <summary>When set, the next <see cref="UploadAsync"/> waits for this task before returning.</summary>
    public Func<UploadCall, CancellationToken, Task<string>>? UploadHandler { get; set; }

    /// <summary>When set, <see cref="DeleteAsync"/> awaits this task before completing.</summary>
    public Func<string, CancellationToken, Task>? DeleteHandler { get; set; }

    public override async Task<string> UploadAsync(
        string vectorStoreId,
        string filename,
        string payload,
        CancellationToken cancellationToken)
    {
        UploadCall call = new(vectorStoreId, filename, payload);
        this.UploadCalls.Add(call);

        if (this.UploadHandler is not null)
        {
            return await this.UploadHandler(call, cancellationToken).ConfigureAwait(false);
        }

        int next = Interlocked.Increment(ref this._fileIdCounter);
        return $"file-{next:D4}";
    }

    public override async Task DeleteAsync(string fileId, CancellationToken cancellationToken)
    {
        this.DeleteCalls.Add(fileId);
        if (this.DeleteHandler is not null)
        {
            await this.DeleteHandler(fileId, cancellationToken).ConfigureAwait(false);
        }
    }

    internal sealed record UploadCall(string VectorStoreId, string Filename, string Payload);
}
