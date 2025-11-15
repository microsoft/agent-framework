// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents a single entry in the durable agent state, which can either be a
/// user/system request or agent response.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(DurableAgentStateRequest), "request")]
[JsonDerivedType(typeof(DurableAgentStateResponse), "response")]
internal abstract class DurableAgentStateEntry
{
    /// <summary>
    /// Gets the correlation ID for this entry.
    /// </summary>
    /// <remarks>
    /// This ID is used to correlate <see cref="DurableAgentStateResponse"/> back to its
    /// <see cref="DurableAgentStateRequest"/>.
    /// </remarks>
    [JsonPropertyName("correlationId")]
    public required string CorrelationId { get; init; }

    /// <summary>
    /// Gets the timestamp when this entry was created.
    /// </summary>
    [JsonPropertyName("createdAt")]
    public required DateTimeOffset CreatedAt { get; init; }

    /// <summary>
    /// Gets the list of messages associated with this entry, in chronological order.
    /// </summary>
    [JsonPropertyName("messages")]
    public IReadOnlyList<DurableAgentStateMessage> Messages { get; init; } = [];

    /// <summary>
    /// Gets any additional data found during deserialization that does not map to known properties.
    /// </summary>
    [JsonExtensionData]
    public IDictionary<string, JsonElement>? ExtensionData { get; set; }
}
