// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the token usage details for a durable agent state response.
/// </summary>
internal sealed class DurableAgentStateUsage
{
    /// <summary>
    /// Gets the number of input tokens used.
    /// </summary>
    [JsonPropertyName("inputTokenCount")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? InputTokenCount { get; init; }

    /// <summary>
    /// Gets the number of output tokens used.
    /// </summary>
    [JsonPropertyName("outputTokenCount")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? OutputTokenCount { get; init; }

    /// <summary>
    /// Gets the total number of tokens used.
    /// </summary>
    [JsonPropertyName("totalTokenCount")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public long? TotalTokenCount { get; init; }

    /// <summary>
    /// Gets any additional data found during deserialization that does not map to known properties.
    /// </summary>
    [JsonExtensionData]
    public IDictionary<string, JsonElement>? ExtensionData { get; set; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateUsage"/> from a <see cref="UsageDetails"/>.
    /// </summary>
    /// <param name="usage">The <see cref="UsageDetails"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateUsage"/> representing the original usage details.</returns>
    [return: NotNullIfNotNull(nameof(usage))]
    public static DurableAgentStateUsage? FromUsage(UsageDetails? usage) =>
        usage is not null
            ? new()
            {
                InputTokenCount = usage.InputTokenCount,
                OutputTokenCount = usage.OutputTokenCount,
                TotalTokenCount = usage.TotalTokenCount
            }
            : null;

    /// <summary>
    /// Converts this <see cref="DurableAgentStateUsage"/> back to a <see cref="UsageDetails"/>.
    /// </summary>
    /// <returns>A <see cref="UsageDetails"/> representing this usage.</returns>
    public UsageDetails ToUsageDetails()
    {
        return new()
        {
            InputTokenCount = this.InputTokenCount,
            OutputTokenCount = this.OutputTokenCount,
            TotalTokenCount = this.TotalTokenCount
        };
    }
}
