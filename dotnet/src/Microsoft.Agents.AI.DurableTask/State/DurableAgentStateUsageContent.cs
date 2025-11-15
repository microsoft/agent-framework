// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the content for a durable agent state message.
/// </summary>
internal sealed class DurableAgentStateUsageContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the usage details.
    /// </summary>
    [JsonPropertyName("usage")]
    public DurableAgentStateUsage Usage { get; init; } = new();

    /// <summary>
    /// Creates a <see cref="DurableAgentStateUsageContent"/> from a <see cref="UsageContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="UsageContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateUsageContent"/> representing the original content.</returns>
    public static DurableAgentStateUsageContent FromUsageContent(UsageContent content)
    {
        return new DurableAgentStateUsageContent()
        {
            Usage = DurableAgentStateUsage.FromUsage(content.Details)
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new UsageContent(this.Usage.ToUsageDetails());
    }
}
