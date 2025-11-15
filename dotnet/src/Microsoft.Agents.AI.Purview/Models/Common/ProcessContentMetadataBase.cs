// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base class for process content metadata.
/// </summary>
[JsonDerivedType(typeof(ProcessConversationMetadata))]
[JsonDerivedType(typeof(ProcessFileMetadata))]
internal abstract class ProcessContentMetadataBase : GraphDataTypeBase
{
    private const string ProcessConversationMetadataDataType = Constants.ODataGraphNamespace + ".processConversationMetadata";

    /// <summary>
    /// Creates a new instance of ProcessContentMetadataBase.
    /// </summary>
    /// <param name="content">The content that will be processed.</param>
    /// <param name="identifier">The unique identifier for the content.</param>
    /// <param name="isTruncated">Indicates if the content is truncated.</param>
    /// <param name="name">The name of the content.</param>
    public ProcessContentMetadataBase(ContentBase content, string identifier, bool isTruncated, string name) : base(ProcessConversationMetadataDataType)
    {
        this.Identifier = identifier;
        this.IsTruncated = isTruncated;
        this.Content = content;
        this.Name = name;
    }

    /// <summary>
    /// Gets or sets the identifier.
    /// Unique id for the content. It is specific to the enforcement plane. Path is used as item unique identifier, e.g., guid of a message in the conversation, file URL, storage file path, message ID, etc.
    /// </summary>
    [JsonPropertyName("identifier")]
    public string Identifier { get; set; }

    /// <summary>
    /// Gets or sets the content.
    /// The content to be processed.
    /// </summary>
    [JsonPropertyName("content")]
    public ContentBase Content { get; set; }

    /// <summary>
    /// Gets or sets the name.
    /// Name of the content, e.g., file name or web page title.
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; set; }

    /// <summary>
    /// Gets or sets the correlationId.
    /// Identifier to group multiple contents.
    /// </summary>
    [JsonPropertyName("correlationId")]
    public string? CorrelationId { get; set; }

    /// <summary>
    /// Gets or sets the sequenceNumber.
    /// Sequence in which the content was originally generated.
    /// </summary>
    [JsonPropertyName("sequenceNumber")]
    public long? SequenceNumber { get; set; }

    /// <summary>
    /// Gets or sets the length.
    /// Content length in bytes.
    /// </summary>
    [JsonPropertyName("length")]
    public long? Length { get; set; }

    /// <summary>
    /// Gets or sets the isTruncated.
    /// Indicates if the original content has been truncated, e.g., to meet text or file size limits.
    /// </summary>
    [JsonPropertyName("isTruncated")]
    public bool IsTruncated { get; set; }

    /// <summary>
    /// Gets or sets the createdDateTime.
    /// When the content was created. E.g., file created time or the time when a message was sent.
    /// </summary>
    [JsonPropertyName("createdDateTime")]
    public DateTimeOffset CreatedDateTime { get; set; } = DateTime.UtcNow;

    /// <summary>
    /// Gets or sets the modifiedDateTime.
    /// When the content was last modified. E.g., file last modified time. For content created on the fly, such as messaging, whenModified and whenCreated are expected to be the same.
    /// </summary>
    [JsonPropertyName("modifiedDateTime")]
    public DateTimeOffset? ModifiedDateTime { get; set; } = DateTime.UtcNow;
}
