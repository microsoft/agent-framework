// Copyright (c) Microsoft. All rights reserved.

using System.Linq.Expressions;
using System.Text.RegularExpressions;
using Microsoft.Extensions.VectorData;

namespace Microsoft.Agents.AI.Samples;

/// <summary>
/// A class that allows for easy storage and retrieval of documents in a Vector Store for Retrieval Augmented Generation (RAG).
/// </summary>
/// <remarks>
/// <para>
/// This class provides an opinionated schema for storing documents in a vector store. It is valuable for simple scenarios
/// where you want to store text + embedding, or a reference to an external document + embedding without needing to customize the schema.
/// If you want to control the schema yourself, use an implementation of <see cref="VectorStoreCollection{TKey, TRecord}"/> directly instead.
/// </para>
/// <para>
/// This class and its related types are currently provided as a sample implementation, but may be promoted to a first-class supported API in future releases.
/// </para>
/// </remarks>
public sealed partial class TextSearchStore : IDisposable
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
    private readonly TextSearchStoreOptions _options;
    private readonly Func<string, ICollection<string>> _wordSegmenter;

    private readonly VectorStoreCollection<object, Dictionary<string, object?>> _vectorStoreRecordCollection;
    private readonly SemaphoreSlim _collectionInitializationLock = new(1, 1);
    private bool _collectionInitialized;
    private bool _disposedValue;

    /// <summary>
    /// Initializes a new instance of the <see cref="TextSearchStore"/> class.
    /// </summary>
    /// <param name="vectorStore">The vector store to store and read the memories from.</param>
    /// <param name="collectionName">The name of the collection in the vector store to store and read the memories from.</param>
    /// <param name="vectorDimensions">The number of dimensions to use for the memory embeddings.</param>
    /// <param name="options">Options to configure the behavior of this class.</param>
    /// <exception cref="NotSupportedException">Thrown if the key type provided is not supported.</exception>
    public TextSearchStore(
        VectorStore vectorStore,
        string collectionName,
        int vectorDimensions,
        TextSearchStoreOptions? options = default)
    {
        // Verify
        if (vectorStore is null)
        {
            throw new ArgumentNullException(nameof(vectorStore));
        }

        if (string.IsNullOrWhiteSpace(collectionName))
        {
            throw new ArgumentException("Collection name cannot be null or whitespace.", nameof(collectionName));
        }

        if (vectorDimensions < 1)
        {
            throw new ArgumentOutOfRangeException(nameof(vectorDimensions), "Vector dimensions must be greater than zero.");
        }

        if (options?.KeyType is not null && options.KeyType != typeof(string) && options.KeyType != typeof(Guid))
        {
            throw new NotSupportedException($"Unsupported key of type '{options.KeyType.Name}'");
        }

        if (options?.KeyType is not null && options.KeyType != typeof(string) && options?.UseSourceIdAsPrimaryKey is true)
        {
            throw new NotSupportedException($"The {nameof(TextSearchStoreOptions.UseSourceIdAsPrimaryKey)} option can only be used when the key type is 'string'.");
        }

        // Assign
        this._vectorStore = vectorStore;
        this._options = options ?? new TextSearchStoreOptions();
        this._wordSegmenter = this._options.WordSegmenter ?? s_defaultWordSegmenter;

        // Create a definition so that we can use the dimensions provided at runtime.
        VectorStoreCollectionDefinition ragDocumentDefinition = new()
        {
            Properties =
            [
                new VectorStoreKeyProperty("Key", this._options.KeyType ?? typeof(string)),
                new VectorStoreDataProperty("Namespaces", typeof(List<string>)) { IsIndexed = true },
                new VectorStoreDataProperty("SourceId", typeof(string)) { IsIndexed = true },
                new VectorStoreDataProperty("Text", typeof(string)) { IsFullTextIndexed = true },
                new VectorStoreDataProperty("SourceName", typeof(string)),
                new VectorStoreDataProperty("SourceLink", typeof(string)),
                new VectorStoreVectorProperty("TextEmbedding", typeof(string), vectorDimensions),
            ]
        };

        this._vectorStoreRecordCollection = this._vectorStore.GetDynamicCollection(collectionName, ragDocumentDefinition);
    }

    /// <summary>
    /// Upserts a batch of text chunks into the vector store.
    /// </summary>
    /// <param name="textChunks">The text chunks to upload.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the documents have been upserted.</returns>
    public async Task UpsertTextAsync(IEnumerable<string> textChunks, CancellationToken cancellationToken = default)
    {
        if (textChunks == null)
        {
            throw new ArgumentNullException(nameof(textChunks));
        }

        var vectorStoreRecordCollection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        var storageDocuments = textChunks.Select(textChunk =>
        {
            // Without text we cannot generate a vector.
            if (string.IsNullOrWhiteSpace(textChunk))
            {
                throw new ArgumentException("One of the provided text chunks is null.", nameof(textChunks));
            }

            return new Dictionary<string, object?>
            {
                { "Key", this.GenerateUniqueKey(null) },
                { "Namespaces", new List<string>() },
                { "Text", textChunk },
                { "TextEmbedding", textChunk },
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
    public async Task UpsertDocumentsAsync(IEnumerable<TextSearchDocument> documents, TextSearchStoreUpsertOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (documents is null)
        {
            throw new ArgumentNullException(nameof(documents));
        }

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
                throw new ArgumentException($"The {nameof(TextSearchDocument.Text)} property must be set.", nameof(document));
            }

            // If we aren't persisting the text, we need a source id or link to refer back to the original document.
            if (options?.DoNotPersistSourceText is true && string.IsNullOrWhiteSpace(document.SourceId) && string.IsNullOrWhiteSpace(document.SourceLink))
            {
                throw new ArgumentException($"Either the {nameof(TextSearchDocument.SourceId)} or {nameof(TextSearchDocument.SourceLink)} properties must be set when the {nameof(TextSearchStoreUpsertOptions.DoNotPersistSourceText)} setting is true.", nameof(document));
            }

            var key = this.GenerateUniqueKey(this._options.UseSourceIdAsPrimaryKey ?? false ? document.SourceId : null);

            return new Dictionary<string, object?>()
            {
                { "Key", key },
                { "Namespaces", document.Namespaces.ToList() },
                { "SourceId", document.SourceId },
                { "Text", options?.DoNotPersistSourceText is true ? null : document.Text },
                { "SourceName", document.SourceName },
                { "SourceLink", document.SourceLink },
                { "TextEmbedding", document.Text },
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
    public async Task<IEnumerable<TextSearchDocument>> SearchAsync(string query, int top, CancellationToken cancellationToken = default)
    {
        var searchResult = await this.SearchCoreAsync(query, top, cancellationToken).ConfigureAwait(false);

        return searchResult.Select(x => new TextSearchDocument()
        {
            Namespaces = (List<string>)x["Namespaces"]!,
            Text = (string?)x["Text"],
            SourceId = (string?)x["SourceId"],
            SourceName = (string?)x["SourceName"],
            SourceLink = (string?)x["SourceLink"],
        });
    }

    /// <summary>
    /// Internal search implementation with hydration of id / link only storage.
    /// </summary>
    /// <param name="query">The text query to find similar documents to.</param>
    /// <param name="top">The maximum number of results to return.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The search results.</returns>
    private async Task<IEnumerable<Dictionary<string, object?>>> SearchCoreAsync(string query, int top, CancellationToken cancellationToken = default)
    {
        // Short circuit if the query is empty.
        if (string.IsNullOrWhiteSpace(query))
        {
            return [];
        }

        var vectorStoreRecordCollection = await this.EnsureCollectionExistsAsync(cancellationToken).ConfigureAwait(false);

        // If the user has not opted out of hybrid search, check if the vector store supports it.
        var hybridSearchCollection = this._options.UseHybridSearch ?? true ?
            vectorStoreRecordCollection.GetService(typeof(IKeywordHybridSearchable<Dictionary<string, object?>>)) as IKeywordHybridSearchable<Dictionary<string, object?>> :
            null;

        // Optional filter to limit the search to a specific namespace.
        Expression<Func<Dictionary<string, object?>, bool>>? filter = string.IsNullOrWhiteSpace(this._options.SearchNamespace) ? null : x => ((List<string>)x["Namespaces"]!).Contains(this._options.SearchNamespace);

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
        List<Dictionary<string, object?>> searchResponseDocs = [];
        await foreach (var searchResponseDoc in searchResult.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            searchResponseDocs.Add(searchResponseDoc.Record);
        }

        // Find any source ids and links for which the text needs to be retrieved.
        var sourceIdsToRetrieve = searchResponseDocs
            .Where(x => string.IsNullOrWhiteSpace((string?)x["Text"]))
            .Select(x => new TextSearchStoreOptions.SourceRetrievalRequest((string?)x["SourceId"], (string?)x["SourceLink"]))
            .ToList();

        // If we have none, we can return early.
        if (sourceIdsToRetrieve.Count == 0)
        {
            return searchResponseDocs;
        }

        if (this._options.SourceRetrievalCallback is null)
        {
            throw new InvalidOperationException($"The {nameof(TextSearchStoreOptions.SourceRetrievalCallback)} option must be set if retrieving documents without stored text.");
        }

        // Retrieve the source text for the documents that need it.
        var retrievalResponses = await this._options.SourceRetrievalCallback(sourceIdsToRetrieve).ConfigureAwait(false) ??
            throw new InvalidOperationException($"The {nameof(TextSearchStoreOptions.SourceRetrievalCallback)} must return a non-null value.");

        // Update the retrieved documents with the retrieved text.
        return searchResponseDocs.GroupJoin(
            retrievalResponses,
            searchResponseDoc => (searchResponseDoc["SourceId"], searchResponseDoc["SourceLink"]),
            retrievalResponse => (retrievalResponse.SourceId, retrievalResponse.SourceLink),
            (searchResponseDoc, textRetrievalResponse) => (searchResponseDoc, textRetrievalResponse))
            .SelectMany(
                joinedSet => joinedSet.textRetrievalResponse.DefaultIfEmpty(),
                (combined, textRetrievalResponse) =>
                {
                    combined.searchResponseDoc["Text"] = textRetrievalResponse?.Text ?? combined.searchResponseDoc["Text"];
                    return combined.searchResponseDoc;
                });
    }

    /// <summary>
    /// Thread safe method to get the collection and ensure that it is created at least once.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The created collection.</returns>
    private async Task<VectorStoreCollection<object, Dictionary<string, object?>>> EnsureCollectionExistsAsync(CancellationToken cancellationToken)
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
    /// <returns>A new unique key.</returns>
    /// <exception cref="NotSupportedException">Thrown if the requested key type is not supported.</exception>
    private object GenerateUniqueKey(string? sourceId)
        => this._options.KeyType switch
        {
            _ when (this._options.KeyType == null || this._options.KeyType == typeof(string)) && !string.IsNullOrWhiteSpace(sourceId) => sourceId!,
            _ when this._options.KeyType == null || this._options.KeyType == typeof(string) => Guid.NewGuid().ToString(),
            _ when this._options.KeyType == typeof(Guid) => Guid.NewGuid(),

            _ => throw new NotSupportedException($"Unsupported key of type '{this._options.KeyType.Name}'")
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
}
