// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Represents an agent identifier.
/// </summary>
internal sealed class AgentId
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentId"/> class.
    /// </summary>
    /// <param name="type">The agent ID type.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="version">The version of the agent.</param>
    public AgentId(AgentIdType type, string name, string version)
    {
        this.Type = type;
        this.Name = name;
        this.Version = version;
    }

    /// <summary>
    /// The agent ID type.
    /// </summary>
    [JsonPropertyName("type")]
    public AgentIdType Type { get; init; }

    /// <summary>
    /// The name of the agent.
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; init; }

    /// <summary>
    /// The version of the agent.
    /// </summary>
    [JsonPropertyName("version")]
    public string Version { get; init; }
}

/// <summary>
/// Represents an agent ID type.
/// </summary>
internal sealed class AgentIdType
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentIdType"/> class.
    /// </summary>
    /// <param name="value">The type value.</param>
    public AgentIdType(string value)
    {
        this.Value = value;
    }

    /// <summary>
    /// The type value.
    /// </summary>
    [JsonPropertyName("type")]
    public string Value { get; init; }
}

/// <summary>
/// Represents an agent reference.
/// </summary>
internal sealed class AgentReference
{
    /// <summary>
    /// The type of the reference (e.g., "agent" or "agent_reference").
    /// </summary>
    [JsonPropertyName("type")]
    public string Type { get; init; } = "agent_reference";

    /// <summary>
    /// The name of the agent.
    /// </summary>
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    /// <summary>
    /// The version of the agent.
    /// </summary>
    [JsonPropertyName("version")]
    public string? Version { get; init; }
}
