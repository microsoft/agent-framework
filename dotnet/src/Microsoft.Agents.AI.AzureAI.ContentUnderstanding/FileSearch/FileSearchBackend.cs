// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Abstract interface for vector-store file operations used by
/// <see cref="ContentUnderstandingContextProvider"/> when <see cref="FileSearchConfig"/> is set.
/// </summary>
/// <remarks>
/// <para>
/// Implementations handle the differences between OpenAI- and Foundry-flavored file upload
/// APIs (e.g. different <c>FileUploadPurpose</c> values). Vector store creation, deletion, and
/// <c>file_search</c> tool construction are <b>not</b> part of this interface — those are
/// managed by the caller and supplied via <see cref="FileSearchConfig"/>.
/// </para>
/// <para>
/// Two built-in concrete backends ship in this package:
/// <see cref="FoundryFileSearchBackend"/> (purpose = <c>assistants</c>) and
/// <see cref="OpenAIFileSearchBackend"/> (purpose = <c>user_data</c>). Custom subclasses are
/// supported for advanced scenarios (e.g. proxying through a different upload service).
/// </para>
/// <para>Mirrors the Python <c>FileSearchBackend</c> abstract base class.</para>
/// </remarks>
public abstract class FileSearchBackend
{
    /// <summary>
    /// Uploads a single payload to a vector store and blocks until indexing has reached a
    /// terminal-successful state.
    /// </summary>
    /// <param name="vectorStoreId">Caller-owned vector store id; must already exist.</param>
    /// <param name="filename">Logical filename used when registering the upload; should end in <c>.md</c> for chunking parity with Python.</param>
    /// <param name="payload">UTF-8 markdown content to upload.</param>
    /// <param name="cancellationToken">Token to honor for cancellation and timeout. Implementations <b>must</b> poll until <see langword="cancelled"/> if the index has not reached <c>Completed</c>.</param>
    /// <returns>The file id of the newly uploaded file (caller must hand this back to <see cref="DeleteAsync"/> for cleanup).</returns>
    /// <exception cref="System.InvalidOperationException">Indexing reached a terminal-failure state.</exception>
    /// <exception cref="System.OperationCanceledException"><paramref name="cancellationToken"/> was signaled before indexing completed.</exception>
    public abstract Task<string> UploadAsync(
        string vectorStoreId,
        string filename,
        string payload,
        CancellationToken cancellationToken);

    /// <summary>
    /// Deletes a previously uploaded file. Deleting the file implicitly removes its association
    /// from any vector stores; the vector store itself is caller-owned and is not modified.
    /// </summary>
    /// <param name="fileId">File id previously returned from <see cref="UploadAsync"/>.</param>
    /// <param name="cancellationToken">Token to honor for cancellation.</param>
    public abstract Task DeleteAsync(string fileId, CancellationToken cancellationToken);
}
