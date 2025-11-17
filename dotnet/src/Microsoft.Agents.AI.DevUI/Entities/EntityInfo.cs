// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DevUI.Entities;

/// <summary>
/// Information about an environment variable required by an entity.
/// </summary>
internal sealed record EnvVarRequirement(
    [property: JsonPropertyName("name")]
    string Name,

    [property: JsonPropertyName("description")]
    string? Description = null,

    [property: JsonPropertyName("required")]
    bool Required = true,

    [property: JsonPropertyName("example")]
    string? Example = null
);

/// <summary>
/// Information about an entity (agent or workflow).
/// </summary>
internal sealed record EntityInfo(
    [property: JsonPropertyName("id")]
    string Id,

    [property: JsonPropertyName("type")]
    string Type,

    [property: JsonPropertyName("name")]
    string Name,

    [property: JsonPropertyName("description")]
    string? Description,

    [property: JsonPropertyName("framework")]
    string Framework,

    [property: JsonPropertyName("tools")]
    List<string> Tools,

    [property: JsonPropertyName("metadata")]
    Dictionary<string, JsonElement> Metadata
)
{
    [JsonPropertyName("source")]
    public string? Source { get; init; } = "di";

    [JsonPropertyName("original_url")]
    public string? OriginalUrl { get; init; }

    // Deployment support
    [JsonPropertyName("deployment_supported")]
    public bool DeploymentSupported { get; init; }

    [JsonPropertyName("deployment_reason")]
    public string? DeploymentReason { get; init; }

    // Agent-specific fields
    [JsonPropertyName("instructions")]
    public string? Instructions { get; init; }

    [JsonPropertyName("model_id")]
    public string? ModelId { get; init; }

    [JsonPropertyName("chat_client_type")]
    public string? ChatClientType { get; init; }

    [JsonPropertyName("context_providers")]
    public List<string>? ContextProviders { get; init; }

    [JsonPropertyName("middleware")]
    public List<string>? Middleware { get; init; }

    [JsonPropertyName("module_path")]
    public string? ModulePath { get; init; }

    // Workflow-specific fields
    [JsonPropertyName("required_env_vars")]
    public List<EnvVarRequirement>? RequiredEnvVars { get; init; }

    [JsonPropertyName("executors")]
    public List<string>? Executors { get; init; }

    [JsonPropertyName("workflow_dump")]
    public JsonElement? WorkflowDump { get; init; }

    [JsonPropertyName("input_schema")]
    public JsonElement? InputSchema { get; init; }

    [JsonPropertyName("input_type_name")]
    public string? InputTypeName { get; init; }

    [JsonPropertyName("start_executor_id")]
    public string? StartExecutorId { get; init; }
};

/// <summary>
/// Response containing a list of discovered entities.
/// </summary>
internal sealed record DiscoveryResponse(
    [property: JsonPropertyName("entities")]
    List<EntityInfo> Entities
);
