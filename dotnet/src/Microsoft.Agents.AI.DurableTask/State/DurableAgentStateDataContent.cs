// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents a durable agent state content that contains data content.
/// </summary>
internal sealed class DurableAgentStateDataContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the URI of the data content.
    /// </summary>
    [JsonPropertyName("uri")]
    public required string Uri { get; init; }

    /// <summary>
    /// Gets the media type of the data content.
    /// </summary>
    [JsonPropertyName("mediaType")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? MediaType { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateDataContent"/> from a <see cref="DataContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="DataContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateDataContent"/> representing the original <see cref="DataContent"/>.</returns>
    public static DurableAgentStateDataContent FromDataContent(DataContent content)
    {
        return new DurableAgentStateDataContent()
        {
            MediaType = content.MediaType,
            Uri = content.Uri
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new DataContent(this.Uri, this.MediaType);
    }
}
