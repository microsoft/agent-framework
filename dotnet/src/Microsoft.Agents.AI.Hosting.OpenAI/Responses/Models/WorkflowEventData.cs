// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents workflow event data for serialization.
/// </summary>
internal sealed class WorkflowEventData
{
    /// <summary>
    /// The type of the workflow event.
    /// </summary>
    [JsonPropertyName("event_type")]
    public required string EventType { get; init; }

    /// <summary>
    /// The event data payload.
    /// </summary>
    [JsonPropertyName("data")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Data { get; init; }

    /// <summary>
    /// The executor ID, if this is an executor event.
    /// </summary>
    [JsonPropertyName("executor_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ExecutorId { get; init; }

    /// <summary>
    /// The timestamp when the event occurred.
    /// </summary>
    [JsonPropertyName("timestamp")]
    public required string Timestamp { get; init; }
}
