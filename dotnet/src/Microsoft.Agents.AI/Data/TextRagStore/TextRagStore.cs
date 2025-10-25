// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Linq.Expressions;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.VectorData;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Data;

/// <summary>
/// A class that allows for easy storage and retrieval of documents in a Vector Store for Retrieval Augmented Generation (RAG).
/// </summary>
/// <remarks>
/// <para>
/// This class provides an opinionated schema for storing documents in a vector store. It is valuable for simple scenarios
/// where you want to store text + embedding, or a reference to an external document + embedding without needing to customize the schema.
/// If you want to control the schema yourself, use an implementation of <see cref="VectorStoreCollection{TKey, TRecord}"/> directly instead.
/// </para>
/// </remarks>
/// <typeparam name="TKey">The key type to use with the vector store. Choose a key type supported by your chosen vector store type. Currently this class only supports string or Guid.</typeparam>
[RequiresDynamicCode("This API is not compatible with NativeAOT.")]
[RequiresUnreferencedCode("This API is not compatible with trimming.")]
public sealed partial class TextRagStore<TKey> : IDisposable
    where TKey : notnull
{
#if NET
    [GeneratedRegex(@"\p{L}+", RegexOptions.IgnoreCase, "en-US")]
    private static partial Regex AnyLanguageWordRegex();

    private static readonly Func<string, ICollection<string>> s_defaultWordSegmenter = text => AnyLanguageWordRegex().Matches(text).Select(x => x.Value).ToList();
#else
    private static readonly Regex s_anyLanguageWordRegex = new(@"\p{L}+", RegexOptions.Compiled);
    private static Regex AnyLanguageWordRegex() => s_anyLanguageWordRegex;

    private static readonly Func<string, ICollection<string>> s_defaultWordSegmenter = text =>
    {
        List<string> words = new();
        foreach (Match word in AnyLanguageWordRegex().Matches(text))
        {
            words.Add(word.Value);
        }
        return words;
    };
#endif

    private readonly VectorStore _vectorStore;
    private readonly TextRagStoreOptions _options;
    private readonly Func<string, ICollection<string>> _wordSegmenter;

    private readonly VectorStoreCollection<TKey, TextRagStorageDocument<TKey>> _vectorStoreRecordCollection;
    private readonly SemaphoreSlim _collectionInitializationLock = new(1, 1);
    private bool _collectionInitialized;
    private bool _disposedValue;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextRagStore{TKey}"/> class.
    /// </summary>
    /// <param name="vectorStore">The vector store to store and read the memories from.</param>
    /// <param name="collectionName">The name of the collection in the vector store to store and read the memories from.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the memory embeddings.</param>
    /// <param name="options">Options to configure the behavior of this class.</param>
    /// <exception cref="NotSupportedException">Thrown if the key type provided is not supported.</exception>
    public TextRagStore(
        VectorStore vectorStore,
        string collectionName,
        int vectorDimensions,
        TextRagStoreOptions? options = default)
    {
        // Verify
        Throw.IfNull(vectorStore);
        Throw.IfNullOrWhitespace(collectionName);
        Throw.IfLessThan(vectorDimensions, 1);

        if (typeof(TKey) != typeof(string) && typeof(TKey) != typeof(Guid))
        {
            throw new NotSupportedException($"Unsupported key of type '{typeof(TKey).Name}'");
        }

        if (typeof(TKey) != typeof(string) && options?.UseSourceIdAsPrimaryKey is true)
        {
            throw new NotSupportedException($"The {nameof(TextRagStoreOptions.UseSourceIdAsPrimaryKey)} option can only be used when the key type is 'string'.");
        }

        // Assign
        this._vectorStore = vectorStore;
        this._options = options ?? new TextRagStoreOptions();
        this._wordSegmenter = this._options.WordSegmenter ?? s_defaultWordSegmenter;

        // Create a definition so that we can use the dimensions provided at runtime.
        VectorStoreCollectionDefinition ragDocumentDefinition = new()
        {
            Properties = new List<VectorStoreProperty>()
            {
                new VectorStoreKeyProperty("Key", typeof(TKey)),
                new VectorStoreDataProperty("Namespaces", typeof(List<string>)) { IsIndexed = true },
                new VectorStoreDataProperty("SourceId", typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty("Text", typeof(string)) { IsFullTextIndexed = true },
                new VectorStoreDataProperty("SourceName", typeof(string)),
                new VectorStoreDataProperty("SourceLink", typeof(string)),
                new VectorStoreVectorProperty("TextEmbedding", typeof(string), vectorDimensions),
            }
        };

        this._vectorStoreRecordCollection = this._vectorStore.GetCollection<TKey, TextRagStorageDocument<TKey>>(collectionName, ragDocumentDefinition);
    }

    /// <summary>
    /// Upserts a batch of text chunks into the vector store.
    /// </summary>
    /// <param name="textChunks">The text chunks to upload.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the documents have been upserted.</returns>
    public async Task UpsertTextAsync(IEnumerable<string> textChunks, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(textChunks);

        var vectorStoreRecordCollection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        var storageDocuments = textChunks.Select(textChunk =>
        {
            // Without text we cannot generate a vector.
            if (string.IsNullOrWhiteSpace(textChunk))
            {
                throw new ArgumentException("One of the provided text chunks is null.", nameof(textChunks));
            }

            return new TextRagStorageDocument<TKey>
            {
                Key = GenerateUniqueKey<TKey>(null),
                Text = textChunk,
                TextEmbedding = textChunk,
            };
        });

        await vectorStoreRecordCollection.UpsertAsync(storageDocuments, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Upserts a batch of documents into the vector store.
    /// </summary>
    /// <param name="documents">The documents to upload.</param>
    /// <param name="options">Optional options to control the upsert behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the documents have been upserted.</returns>
    public async Task UpsertDocumentsAsync(IEnumerable<TextRagDocument> documents, TextRagStoreUpsertOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(documents);

        var vectorStoreRecordCollection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        var storageDocuments = documents.Select(document =>
        {
            if (document is null)
            {
                throw new ArgumentNullException(nameof(documents), "One of the provided documents is null.");
            }

            // Without text we cannot generate a vector.
            if (string.IsNullOrWhiteSpace(document.Text))
            {
                throw new ArgumentException($"The {nameof(TextRagDocument.Text)} property must be set.", nameof(document));
            }

            // If we aren't persisting the text, we need a source id or link to refer back to the original document.
            if (options?.DoNotPersistSourceText is true && string.IsNullOrWhiteSpace(document.SourceId) && string.IsNullOrWhiteSpace(document.SourceLink))
            {
                throw new ArgumentException($"Either the {nameof(TextRagDocument.SourceId)} or {nameof(TextRagDocument.SourceLink)} properties must be set when the {nameof(TextRagStoreUpsertOptions.DoNotPersistSourceText)} setting is true.", nameof(document));
            }

            var key = GenerateUniqueKey<TKey>(this._options.UseSourceIdAsPrimaryKey ?? false ? document.SourceId : null);

            return new TextRagStorageDocument<TKey>
            {
                Key = key,
                Namespaces = document.Namespaces.ToList(),
                SourceId = document.SourceId,
                Text = options?.DoNotPersistSourceText is true ? null : document.Text,
                SourceName = document.SourceName,
                SourceLink = document.SourceLink,
                TextEmbedding = document.Text,
            };
        });

        await vectorStoreRecordCollection.UpsertAsync(storageDocuments, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Search the database for documents similar to the provided query.
    /// </summary>
    /// <param name="query">The text query to find similar documents to.</param>
    /// <param name="top">The maximum number of results to return.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The search results.</returns>
    public async Task<IEnumerable<TextRagDocument>> SearchAsync(string query, int top, CancellationToken cancellationToken = default)
    {
        var searchResult = await this.SearchCoreAsync(query, top, cancellationToken).ConfigureAwait(false);

        return searchResult.Select(x => new TextRagDocument()
        {
            Namespaces = x.Namespaces,
            Text = x.Text,
            SourceId = x.SourceId,
            SourceName = x.SourceName,
            SourceLink = x.SourceLink,
        });
    }

    /// <summary>
    /// Internal search implementation with hydration of id / link only storage.
    /// </summary>
    /// <param name="query">The text query to find similar documents to.</param>
    /// <param name="top">The maximum number of results to return.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The search results.</returns>
    private async Task<IEnumerable<TextRagStorageDocument<TKey>>> SearchCoreAsync(string query, int top, CancellationToken cancellationToken = default)
    {
        // Short circuit if the query is empty.
        if (string.IsNullOrWhiteSpace(query))
        {
            return Enumerable.Empty<TextRagStorageDocument<TKey>>();
        }

        var vectorStoreRecordCollection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        // If the user has not opted out of hybrid search, check if the vector store supports it.
        var hybridSearchCollection = this._options.UseHybridSearch ?? true ?
            vectorStoreRecordCollection.GetService(typeof(IKeywordHybridSearchable<TextRagStorageDocument<TKey>>)) as IKeywordHybridSearchable<TextRagStorageDocument<TKey>> :
            null;

        // Optional filter to limit the search to a specific namespace.
        Expression<Func<TextRagStorageDocument<TKey>, bool>>? filter = string.IsNullOrWhiteSpace(this._options.SearchNamespace) ? null : x => x.Namespaces.Contains(this._options.SearchNamespace);

        // Execute a hybrid search if possible, otherwise perform a regular vector search.
        var searchResult = hybridSearchCollection is null
            ? vectorStoreRecordCollection.SearchAsync(
                query,
                top,
                options: new()
                {
                    Filter = filter,
                },
                cancellationToken: cancellationToken)
            : hybridSearchCollection.HybridSearchAsync(
                query,
                this._wordSegmenter(query),
                top,
                options: new()
                {
                    Filter = filter,
                },
                cancellationToken: cancellationToken);

        // Retrieve the documents from the search results.
        List<TextRagStorageDocument<TKey>> searchResponseDocs = new();
        await foreach (var searchResponseDoc in searchResult.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            searchResponseDocs.Add(searchResponseDoc.Record);
        }

        // Find any source ids and links for which the text needs to be retrieved.
        var sourceIdsToRetrieve = searchResponseDocs
            .Where(x => string.IsNullOrWhiteSpace(x.Text))
            .Select(x => new TextRagStoreOptions.SourceRetrievalRequest(x.SourceId, x.SourceLink))
            .ToList();

        // If we have none, we can return early.
        if (sourceIdsToRetrieve.Count == 0)
        {
            return searchResponseDocs;
        }

        if (this._options.SourceRetrievalCallback is null)
        {
            throw new InvalidOperationException($"The {nameof(TextRagStoreOptions.SourceRetrievalCallback)} option must be set if retrieving documents without stored text.");
        }

        // Retrieve the source text for the documents that need it.
        var retrievalResponses = await this._options.SourceRetrievalCallback(sourceIdsToRetrieve).ConfigureAwait(false);

        if (retrievalResponses is null)
        {
            throw new InvalidOperationException($"The {nameof(TextRagStoreOptions.SourceRetrievalCallback)} must return a non-null value.");
        }

        // Update the retrieved documents with the retrieved text.
        return searchResponseDocs.GroupJoin(
            retrievalResponses,
            searchResponseDoc => (searchResponseDoc.SourceId, searchResponseDoc.SourceLink),
            retrievalResponse => (retrievalResponse.SourceId, retrievalResponse.SourceLink),
            (searchResponseDoc, textRetrievalResponse) => (searchResponseDoc, textRetrievalResponse))
            .SelectMany(
                joinedSet => joinedSet.textRetrievalResponse.DefaultIfEmpty(),
                (combined, textRetrievalResponse) =>
                {
                    combined.searchResponseDoc.Text = textRetrievalResponse?.Text ?? combined.searchResponseDoc.Text;
                    return combined.searchResponseDoc;
                });
    }

    /// <summary>
    /// Thread safe method to get the collection and ensure that it is created at least once.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The created collection.</returns>
    private async Task<VectorStoreCollection<TKey, TextRagStorageDocument<TKey>>> EnsureCollectionExistsAsync(CancellationToken cancellationToken)
    {
        // Return immediately if the collection is already created, no need to do any locking in this case.
        if (this._collectionInitialized)
        {
            return this._vectorStoreRecordCollection;
        }

        // Wait on a lock to ensure that only one thread can create the collection.
        await this._collectionInitializationLock.WaitAsync(cancellationToken).ConfigureAwait(false);

        // If multiple threads waited on the lock, and the first already created the collection,
        // we can return immediately without doing any work in subsequent threads.
        if (this._collectionInitialized)
        {
            this._collectionInitializationLock.Release();
            return this._vectorStoreRecordCollection;
        }

        // Only the winning thread should reach this point and create the collection.
        try
        {
            await this._vectorStoreRecordCollection.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);
            this._collectionInitialized = true;
        }
        finally
        {
            this._collectionInitializationLock.Release();
        }

        return this._vectorStoreRecordCollection;
    }

    /// <summary>
    /// Generates a unique key for the RAG document.
    /// </summary>
    /// <param name="sourceId">Source id of the source document for this RAG document.</param>
    /// <typeparam name="TDocumentKey">The type of the key to use, since different databases require/support different keys.</typeparam>
    /// <returns>A new unique key.</returns>
    /// <exception cref="NotSupportedException">Thrown if the requested key type is not supported.</exception>
    private static TDocumentKey GenerateUniqueKey<TDocumentKey>(string? sourceId)
        => typeof(TDocumentKey) switch
        {
            _ when typeof(TDocumentKey) == typeof(string) && !string.IsNullOrWhiteSpace(sourceId) => (TDocumentKey)(object)sourceId!,
            _ when typeof(TDocumentKey) == typeof(string) => (TDocumentKey)(object)Guid.NewGuid().ToString(),
            _ when typeof(TDocumentKey) == typeof(Guid) => (TDocumentKey)(object)Guid.NewGuid(),

            _ => throw new NotSupportedException($"Unsupported key of type '{typeof(TDocumentKey).Name}'")
        };

    /// <inheritdoc/>
    private void Dispose(bool disposing)
    {
        if (!this._disposedValue)
        {
            if (disposing)
            {
                this._vectorStoreRecordCollection.Dispose();
                this._collectionInitializationLock.Dispose();
            }

            this._disposedValue = true;
        }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        // Do not change this code. Put cleanup code in 'Dispose(bool disposing)' method
        this.Dispose(disposing: true);
        GC.SuppressFinalize(this);
    }

    /// <summary>
    /// The data model to use for storing RAG documents in the vector store.
    /// </summary>
    /// <typeparam name="TDocumentKey">The type of the key to use, since different databases require/support different keys.</typeparam>
    internal sealed class TextRagStorageDocument<TDocumentKey>
    {
        /// <summary>
        /// Gets or sets a unique identifier for the memory document.
        /// </summary>
        public TDocumentKey Key { get; set; } = default!;

        /// <summary>
        /// Gets or sets an optional list of namespaces that the document should belong to.
        /// </summary>
        /// <remarks>
        /// A namespace is a logical grouping of documents, e.g. may include a group id to scope the document to a specific group of users.
        /// </remarks>
        public List<string> Namespaces { get; set; } = [];

        /// <summary>
        /// Gets or sets the content as text.
        /// </summary>
        public string? Text { get; set; }

        /// <summary>
        /// Gets or sets an optional source ID for the document.
        /// </summary>
        /// <remarks>
        /// This ID should be unique within the collection that the document is stored in, and can
        /// be used to map back to the source artifact for this document.
        /// If updates need to be made later or the source document was deleted and this document
        /// also needs to be deleted, this id can be used to find the document again.
        /// </remarks>
        public string? SourceId { get; set; }

        /// <summary>
        /// Gets or sets an optional name for the source document.
        /// </summary>
        /// <remarks>
        /// This can be used to provide display names for citation links when the document is referenced as
        /// part of a response to a query.
        /// </remarks>
        public string? SourceName { get; set; }

        /// <summary>
        /// Gets or sets an optional link back to the source of the document.
        /// </summary>
        /// <remarks>
        /// This can be used to provide citation links when the document is referenced as
        /// part of a response to a query.
        /// </remarks>
        public string? SourceLink { get; set; }

        /// <summary>
        /// Gets or sets the text that will be used to generate the embedding for the document.
        /// </summary>
        public string? TextEmbedding { get; set; }
    }
}
