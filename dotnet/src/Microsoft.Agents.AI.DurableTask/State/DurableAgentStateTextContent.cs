// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the text content for a durable agent state entry.
/// </summary>
internal sealed class DurableAgentStateTextContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the text message content.
    /// </summary>
    [JsonPropertyName("text")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public required string? Text { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateTextContent"/> from a <see cref="TextContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="TextContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateTextContent"/> representing the original content.</returns>
    public static DurableAgentStateTextContent FromTextContent(TextContent content)
    {
        return new DurableAgentStateTextContent()
        {
            Text = content.Text
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new TextContent(this.Text);
    }
}
