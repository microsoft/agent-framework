// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents metadata for a file content to be processed by the Purview SDK.
/// </summary>
internal sealed class ProcessFileMetadata : ProcessContentMetadataBase
{
    private const string ProcessFileMetadataDataType = Constants.ODataGraphNamespace + ".processFileMetadata";

    /// <summary>
    /// Initializes a new instance of the <see cref="ProcessFileMetadata"/> class.
    /// </summary>
    public ProcessFileMetadata(ContentBase contentBase, string identifier, bool isTruncated, string name) : base(contentBase, identifier, isTruncated, name)
    {
        this.DataType = ProcessFileMetadataDataType;
    }

    /// <summary>
    /// Gets or sets the owner ID.
    /// </summary>
    [JsonPropertyName("ownerId")]
    public string? OwnerId { get; set; }
}
