// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Samples;

/// <summary>
/// Contains options for the <see cref="TextSearchStore"/>.
/// </summary>
public sealed class TextSearchStoreOptions
{
    /// <summary>
    /// Gets or sets an optional namespace to pre-filter the possible
    /// records with when doing a vector search.
    /// </summary>
    public string? SearchNamespace { get; init; }

    /// <summary>
    /// Gets or sets a value indicating whether to use the source ID as the primary key for records.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Using the source ID as the primary key allows for easy updates from the source for any changed
    /// records, since those records can just be upserted again, and will overwrite the previous version
    /// of the same record.
    /// </para>
    /// <para>
    /// This setting can only be used when the chosen key type is a string.
    /// </para>
    /// </remarks>
    /// <value>
    /// Defaults to <c>false</c> if not set.
    /// </value>
    public bool? UseSourceIdAsPrimaryKey { get; init; }

    /// <summary>
    /// Gets or sets a value indicating whether to use hybrid search if it is available for the provided vector store.
    /// </summary>
    /// <value>
    /// Defaults to <c>true</c> if not set.
    /// </value>
    public bool? UseHybridSearch { get; init; }

    /// <summary>
    /// Gets or sets a word segmenter function to split search text into separate words for the purposes of hybrid search.
    /// This will not be used if <see cref="UseHybridSearch"/> is set to <c>false</c>.
    /// </summary>
    /// <remarks>
    /// Defaults to a simple text-character-based segmenter that splits the text by any character that is not a text character.
    /// </remarks>
    public Func<string, ICollection<string>>? WordSegmenter { get; init; }

    /// <summary>
    /// Gets or sets the type of key to use for records in the text search store.
    /// </summary>
    /// <remarks>
    /// Make sure to pick a key type that is supported by the underlying vector store.
    /// Note that you have to choose <see cref="string"/> when using <see cref="UseSourceIdAsPrimaryKey"/>.
    /// </remarks>
    /// <value>Defaults to <see cref="string"/> if not set. Only <see cref="string"/> and <see cref="Guid"/> is currently supported.</value>
    public Type? KeyType { get; init; }

    /// <summary>
    /// Gets or sets an optional callback to load the source text using the source id or source link
    /// if the source text is not persisted in the database.
    /// </summary>
    /// <remarks>
    /// The response should include the source id or source link, as provided in the request,
    /// plus the source text loaded from the source.
    /// </remarks>
    public Func<List<SourceRetrievalRequest>, Task<IEnumerable<SourceRetrievalResponse>>>? SourceRetrievalCallback { get; init; }

    /// <summary>
    /// Represents a request to the <see cref="SourceRetrievalCallback"/>.
    /// </summary>
    public sealed class SourceRetrievalRequest
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="SourceRetrievalRequest"/> class.
        /// </summary>
        /// <param name="sourceId">The source ID of the document to retrieve.</param>
        /// <param name="sourceLink">The source link of the document to retrieve.</param>
        public SourceRetrievalRequest(string? sourceId, string? sourceLink)
        {
            this.SourceId = sourceId;
            this.SourceLink = sourceLink;
        }

        /// <summary>
        /// Gets or sets the source ID of the document to retrieve.
        /// </summary>
        public string? SourceId { get; set; }

        /// <summary>
        /// Gets or sets the source link of the document to retrieve.
        /// </summary>
        public string? SourceLink { get; set; }
    }

    /// <summary>
    /// Represents a response from the <see cref="SourceRetrievalCallback"/>.
    /// </summary>
    public sealed class SourceRetrievalResponse
    {
        /// <summary>
        /// Initializes a new instance of the <see cref="SourceRetrievalResponse"/> class.
        /// </summary>
        /// <param name="request">The request matching this response.</param>
        /// <param name="text">The source text that was retrieved.</param>
        public SourceRetrievalResponse(SourceRetrievalRequest request, string text)
        {
            if (request == null)
            {
                throw new ArgumentNullException(nameof(request));
            }

            if (text == null)
            {
                throw new ArgumentNullException(nameof(text));
            }

            this.SourceId = request.SourceId;
            this.SourceLink = request.SourceLink;
            this.Text = text;
        }

        /// <summary>
        /// Gets or sets the source ID of the document that was retrieved.
        /// </summary>
        public string? SourceId { get; set; }

        /// <summary>
        /// Gets or sets the source link of the document that was retrieved.
        /// </summary>
        public string? SourceLink { get; set; }

        /// <summary>
        /// Gets or sets the source text of the document that was retrieved.
        /// </summary>
        public string Text { get; set; }
    }
}
