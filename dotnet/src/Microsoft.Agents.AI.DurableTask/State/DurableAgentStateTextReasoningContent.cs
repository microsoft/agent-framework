// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the text reasoning content for a durable agent state entry.
/// </summary>
internal sealed class DurableAgentStateTextReasoningContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the text reasoning content.
    /// </summary>
    [JsonPropertyName("text")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Text { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateTextReasoningContent"/> from a <see cref="TextReasoningContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="TextReasoningContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateTextReasoningContent"/> representing the original content.</returns>
    public static DurableAgentStateTextReasoningContent FromTextReasoningContent(TextReasoningContent content)
    {
        return new DurableAgentStateTextReasoningContent()
        {
            Text = content.Text
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new TextReasoningContent(this.Text);
    }
}
