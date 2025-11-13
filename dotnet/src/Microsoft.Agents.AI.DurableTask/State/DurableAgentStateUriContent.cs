// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents URI content for a durable agent state message.
/// </summary>
internal sealed class DurableAgentStateUriContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the URI of the content.
    /// </summary>
    [JsonPropertyName("uri")]
    public required Uri Uri { get; init; }

    /// <summary>
    /// Gets the media type of the content.
    /// </summary>
    [JsonPropertyName("mediaType")]
    public required string MediaType { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateUriContent"/> from a <see cref="UriContent"/>.
    /// </summary>
    /// <param name="uriContent">The <see cref="UriContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateUriContent"/> representing the original content.</returns>
    public static DurableAgentStateUriContent FromUriContent(UriContent uriContent)
    {
        return new DurableAgentStateUriContent()
        {
            MediaType = uriContent.MediaType,
            Uri = uriContent.Uri
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new UriContent(this.Uri, this.MediaType);
    }
}
