// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Text;
using OpenAI;
using OpenAI.Files;
using OpenAI.VectorStores;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Shared implementation for OpenAI-compatible file-search backends — both
/// <see cref="FoundryFileSearchBackend"/> and <see cref="OpenAIFileSearchBackend"/> derive from
/// this base. The only public surface difference between the two is the
/// <see cref="Purpose"/> property; the upload + indexing-poll + delete logic lives here.
/// </summary>
/// <remarks>
/// <para>
/// Mirrors Python <c>_OpenAICompatBackend</c>. The poll loop (after
/// <c>AddFileToVectorStoreAsync</c>) is hand-written because OpenAI .NET 2.10 does not expose
/// a <c>create_and_poll</c> equivalent; without polling, <c>file_search</c> queries can race
/// vector-store ingestion and return no results immediately after upload.
/// </para>
/// <para>
/// This type is <see langword="public"/> only because the two shipped concrete subclasses
/// (<see cref="FoundryFileSearchBackend"/> and <see cref="OpenAIFileSearchBackend"/>) are
/// public and CLR accessibility rules forbid a public class deriving from a less-accessible
/// base. External callers are not expected to subclass it directly; if you need a custom
/// upload flow, derive from <see cref="FileSearchBackend"/> instead.
/// </para>
/// </remarks>
public abstract class OpenAICompatFileSearchBackendBase : FileSearchBackend
{
    private static readonly TimeSpan[] s_pollDelays =
    {
        TimeSpan.FromMilliseconds(500),
        TimeSpan.FromSeconds(1),
        TimeSpan.FromSeconds(2),
        TimeSpan.FromSeconds(5),
    };

    private readonly OpenAIClient _openAiClient;

    /// <summary>
    /// Initializes the shared OpenAI-compatible backend with an existing
    /// <see cref="OpenAIClient"/>. The constructor is <see langword="protected"/> because this
    /// base type is not intended for direct external instantiation — derive from one of the
    /// two shipped subclasses or from <see cref="FileSearchBackend"/> instead.
    /// </summary>
    protected OpenAICompatFileSearchBackendBase(OpenAIClient openAiClient)
    {
        this._openAiClient = openAiClient ?? throw new ArgumentNullException(nameof(openAiClient));
    }

    /// <summary>The <c>FileUploadPurpose</c> value used when registering files. Foundry uses <c>assistants</c>; raw OpenAI uses <c>user_data</c>.</summary>
    protected abstract FileUploadPurpose Purpose { get; }

    /// <inheritdoc/>
    public sealed override async Task<string> UploadAsync(
        string vectorStoreId,
        string filename,
        string payload,
        CancellationToken cancellationToken)
    {
        _ = vectorStoreId ?? throw new ArgumentNullException(nameof(vectorStoreId));
        _ = filename ?? throw new ArgumentNullException(nameof(filename));
        _ = payload ?? throw new ArgumentNullException(nameof(payload));

        byte[] bytes = Encoding.UTF8.GetBytes(payload);

        // MemoryStream's Dispose is non-blocking, so the regular (sync) using is sufficient
        // even across async — and avoids CA2007 on a pointless awaited dispose.
        using var stream = new MemoryStream(bytes, writable: false);

#pragma warning disable OPENAI001 // FileUploadPurpose members + VectorStoreClient/VectorStoreFileStatus are experimental in OpenAI 2.10; intentional inside the backend boundary.
        OpenAIFileClient fileClient = this._openAiClient.GetOpenAIFileClient();
        OpenAIFile uploadedFile = await fileClient
            .UploadFileAsync(stream, filename, this.Purpose, cancellationToken)
            .ConfigureAwait(false);

        string fileId = uploadedFile.Id;

        VectorStoreClient vectorClient = this._openAiClient.GetVectorStoreClient();
        VectorStoreFile association = await vectorClient
            .AddFileToVectorStoreAsync(vectorStoreId, fileId, cancellationToken)
            .ConfigureAwait(false);

        VectorStoreFileStatus status = association.Status;
        int delayIndex = 0;
        while (status is VectorStoreFileStatus.InProgress or VectorStoreFileStatus.Unknown)
        {
            cancellationToken.ThrowIfCancellationRequested();
            TimeSpan delay = s_pollDelays[Math.Min(delayIndex, s_pollDelays.Length - 1)];
            await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            delayIndex++;
            VectorStoreFile refreshed = await vectorClient
                .GetVectorStoreFileAsync(vectorStoreId, fileId, cancellationToken)
                .ConfigureAwait(false);
            association = refreshed;
            status = refreshed.Status;
        }

        if (status != VectorStoreFileStatus.Completed)
        {
            string? lastError = association.LastError?.Message;
            throw new InvalidOperationException(
                $"Vector store file '{fileId}' ended in status '{status}': {lastError ?? "<no error message>"}");
        }
#pragma warning restore OPENAI001

        return fileId;
    }

    /// <inheritdoc/>
    public sealed override async Task DeleteAsync(string fileId, CancellationToken cancellationToken)
    {
        _ = fileId ?? throw new ArgumentNullException(nameof(fileId));

        OpenAIFileClient fileClient = this._openAiClient.GetOpenAIFileClient();
        _ = await fileClient.DeleteFileAsync(fileId, cancellationToken).ConfigureAwait(false);
    }
}
