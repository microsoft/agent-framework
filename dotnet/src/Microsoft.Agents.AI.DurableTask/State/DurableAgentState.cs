// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the state of a durable agent, including its conversation history.
/// </summary>
[JsonConverter(typeof(DurableAgentStateJsonConverter))]
internal sealed class DurableAgentState
{
    /// <summary>
    /// Gets the data of the durable agent.
    /// </summary>
    [JsonPropertyName("data")]
    public DurableAgentStateData Data { get; init; } = new();

    /// <summary>
    /// Gets the schema version of the durable agent state.
    /// </summary>
    /// <remarks>
    /// The version is specified in semver (i.e. "major.minor.patch") format.
    /// </remarks>
    [JsonPropertyName("schemaVersion")]
    public string SchemaVersion { get; init; } = "1.0.0";
}
