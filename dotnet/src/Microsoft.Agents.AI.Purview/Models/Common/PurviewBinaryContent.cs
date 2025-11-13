// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents a binary content item to be processed.
/// </summary>
internal sealed class PurviewBinaryContent : ContentBase
{
    private const string BinaryContentDataType = Constants.ODataGraphNamespace + ".binaryContent";

    /// <summary>
    /// Initializes a new instance of the <see cref="PurviewBinaryContent"/> class.
    /// </summary>
    /// <param name="data">The binary content in byte array format.</param>
    public PurviewBinaryContent(byte[] data) : base(BinaryContentDataType)
    {
        this.Data = data;
    }

    /// <summary>
    /// Gets or sets the binary data.
    /// </summary>
    [JsonPropertyName("data")]
    public byte[] Data { get; set; }
}
