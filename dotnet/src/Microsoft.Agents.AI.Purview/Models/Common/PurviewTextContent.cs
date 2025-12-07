// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents a text content item to be processed.
/// </summary>
internal sealed class PurviewTextContent : ContentBase
{
    private const string TextContentDataType = Constants.ODataGraphNamespace + ".textContent";

    /// <summary>
    /// Initializes a new instance of the <see cref="PurviewTextContent"/> class.
    /// </summary>
    /// <param name="data">The text content in string format.</param>
    public PurviewTextContent(string data) : base(TextContentDataType)
    {
        this.Data = data;
    }

    /// <summary>
    /// Gets or sets the text data.
    /// </summary>
    [JsonPropertyName("data")]
    public string Data { get; set; }
}
