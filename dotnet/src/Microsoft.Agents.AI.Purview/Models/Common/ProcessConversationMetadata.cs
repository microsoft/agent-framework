// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Represents metadata for conversation content to be processed by the Purview SDK.
/// </summary>
internal sealed class ProcessConversationMetadata : ProcessContentMetadataBase
{
    private const string ProcessConversationMetadataDataType = Constants.ODataGraphNamespace + ".processConversationMetadata";

    /// <summary>
    /// Initializes a new instance of the <see cref="ProcessConversationMetadata"/> class.
    /// </summary>
    public ProcessConversationMetadata(ContentBase contentBase, string identifier, bool isTruncated, string name) : base(contentBase, identifier, isTruncated, name)
    {
        this.DataType = ProcessConversationMetadataDataType;
    }

    /// <summary>
    /// Gets or sets the parent message ID for nested conversations.
    /// </summary>
    [JsonPropertyName("parentMessageId")]
    public string? ParentMessageId { get; set; }

    /// <summary>
    /// Gets or sets the accessed resources during message generation for bot messages.
    /// </summary>
    [JsonPropertyName("accessedResources_v2")]
    public List<AccessedResourceDetails>? AccessedResources { get; set; }

    /// <summary>
    /// Gets or sets the plugins used during message generation for bot messages.
    /// </summary>
    [JsonPropertyName("plugins")]
    public List<AIInteractionPlugin>? Plugins { get; set; }

    /// <summary>
    /// Gets or sets the collection of AI agent information.
    /// </summary>
    [JsonPropertyName("agents")]
    public List<AIAgentInfo>? Agents { get; set; }
}
