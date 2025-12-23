// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the unknown content for a durable agent state entry.
/// </summary>
internal sealed class DurableAgentStateUnknownContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the serialized unknown content.
    /// </summary>
    [JsonPropertyName("content")]
    public required JsonElement Content { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateUnknownContent"/> from an <see cref="AIContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="AIContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateUnknownContent"/> representing the original content.</returns>
    public static DurableAgentStateUnknownContent FromUnknownContent(AIContent content)
    {
        return new DurableAgentStateUnknownContent()
        {
            Content = JsonSerializer.SerializeToElement(
                value: content,
                jsonTypeInfo: AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent)))
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        AIContent? content = this.Content.Deserialize(
            jsonTypeInfo: AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent))) as AIContent;

        return content ?? throw new InvalidOperationException($"The content '{this.Content}' is not valid AI content.");
    }
}
