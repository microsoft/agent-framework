// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Internal wire-format models for the OpenAI Evals API.
/// </summary>
/// <remarks>
/// <para>
/// The OpenAI .NET SDK (as of 2.9.1) marks its <c>EvaluationClient</c> as experimental
/// and exposes only protocol-level methods that accept <c>BinaryContent</c> and return
/// <c>ClientResult</c> — no strongly typed request or response models are provided.
/// </para>
/// <para>
/// These internal models replace hand-built <c>Dictionary&lt;string, object&gt;</c> payloads
/// with compile-time–safe types that are serialized via <see cref="System.Text.Json"/>.
/// When the SDK ships typed models, these should be replaced.
/// </para>
/// </remarks>
// -----------------------------------------------------------------------
// Message content items (polymorphic by "type" discriminator)
// -----------------------------------------------------------------------

[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(WireTextContent), "text")]
[JsonDerivedType(typeof(WireImageContent), "input_image")]
[JsonDerivedType(typeof(WireToolCallContent), "tool_call")]
[JsonDerivedType(typeof(WireToolResultContent), "tool_result")]
internal abstract class WireContentItem
{
}

internal sealed class WireTextContent : WireContentItem
{
    [JsonPropertyName("text")]
    public required string Text { get; init; }
}

internal sealed class WireImageContent : WireContentItem
{
    [JsonPropertyName("image_url")]
    public required string ImageUrl { get; init; }

    [JsonPropertyName("detail")]
    public string Detail { get; init; } = "auto";
}

internal sealed class WireToolCallContent : WireContentItem
{
    [JsonPropertyName("tool_call_id")]
    public required string ToolCallId { get; init; }

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("arguments")]
    public IDictionary<string, object?>? Arguments { get; init; }
}

internal sealed class WireToolResultContent : WireContentItem
{
    [JsonPropertyName("tool_result")]
    public required object ToolResult { get; init; }
}

// -----------------------------------------------------------------------
// Message
// -----------------------------------------------------------------------

internal sealed class WireMessage
{
    [JsonPropertyName("role")]
    public required string Role { get; init; }

    [JsonPropertyName("content")]
    public required List<WireContentItem> Content { get; init; }

    [JsonPropertyName("tool_call_id")]
    public string? ToolCallId { get; init; }
}

// -----------------------------------------------------------------------
// Eval item payload (a single JSONL row sent to the Evals API)
// -----------------------------------------------------------------------

internal sealed class WireEvalItemPayload
{
    [JsonPropertyName("query")]
    public required string Query { get; init; }

    [JsonPropertyName("response")]
    public required string Response { get; init; }

    [JsonPropertyName("query_messages")]
    public required List<WireMessage> QueryMessages { get; init; }

    [JsonPropertyName("response_messages")]
    public required List<WireMessage> ResponseMessages { get; init; }

    [JsonPropertyName("context")]
    public string? Context { get; init; }

    [JsonPropertyName("tool_definitions")]
    public List<WireToolDefinition>? ToolDefinitions { get; init; }
}

internal sealed class WireToolDefinition
{
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    [JsonPropertyName("description")]
    public string? Description { get; init; }

    [JsonPropertyName("parameters")]
    public object? Parameters { get; init; }
}

// -----------------------------------------------------------------------
// Testing criteria (evaluator definitions within an eval)
// -----------------------------------------------------------------------

internal sealed class WireTestingCriterion
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "azure_ai_evaluator";

    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("evaluator_name")]
    public required string EvaluatorName { get; init; }

    [JsonPropertyName("initialization_parameters")]
    public required WireInitParams InitializationParameters { get; init; }

    [JsonPropertyName("data_mapping")]
    public Dictionary<string, string>? DataMapping { get; init; }
}

internal sealed class WireInitParams
{
    [JsonPropertyName("deployment_name")]
    public required string DeploymentName { get; init; }
}

// -----------------------------------------------------------------------
// Item schema (for custom JSONL data source definitions)
// -----------------------------------------------------------------------

internal sealed class WireItemSchema
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "object";

    [JsonPropertyName("properties")]
    public required Dictionary<string, WireSchemaProperty> Properties { get; init; }

    [JsonPropertyName("required")]
    public required List<string> Required { get; init; }
}

internal sealed class WireSchemaProperty
{
    [JsonPropertyName("type")]
    public required string Type { get; init; }
}

// -----------------------------------------------------------------------
// Create evaluation request
// -----------------------------------------------------------------------

internal sealed class WireCreateEvalRequest
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("data_source_config")]
    public required object DataSourceConfig { get; init; }

    [JsonPropertyName("testing_criteria")]
    public required List<WireTestingCriterion> TestingCriteria { get; init; }
}

// Data source configuration variants

internal sealed class WireCustomDataSourceConfig
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "custom";

    [JsonPropertyName("item_schema")]
    public required WireItemSchema ItemSchema { get; init; }

    [JsonPropertyName("include_sample_schema")]
    public bool IncludeSampleSchema { get; init; } = true;
}

internal sealed class WireAzureAiDataSourceConfig
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "azure_ai_source";

    [JsonPropertyName("scenario")]
    public required string Scenario { get; init; }
}

// -----------------------------------------------------------------------
// Create evaluation run request
// -----------------------------------------------------------------------

internal sealed class WireCreateRunRequest
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("data_source")]
    public required object DataSource { get; init; }
}

// -----------------------------------------------------------------------
// Data source variants (used in run requests)
// -----------------------------------------------------------------------

internal sealed class WireJsonlDataSource
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "jsonl";

    [JsonPropertyName("source")]
    public required WireFileContentSource Source { get; init; }
}

internal sealed class WireFileContentSource
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "file_content";

    [JsonPropertyName("content")]
    public required List<WireItemWrapper> Content { get; init; }
}

internal sealed class WireItemWrapper
{
    [JsonPropertyName("item")]
    public required object Item { get; init; }
}

internal sealed class WireResponsesDataSource
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "azure_ai_responses";

    [JsonPropertyName("item_generation_params")]
    public required WireResponseRetrievalParams ItemGenerationParams { get; init; }
}

internal sealed class WireResponseRetrievalParams
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "response_retrieval";

    [JsonPropertyName("data_mapping")]
    public required Dictionary<string, string> DataMapping { get; init; }

    [JsonPropertyName("source")]
    public required WireFileContentSource Source { get; init; }
}

internal sealed class WireTracesDataSource
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "azure_ai_traces";

    [JsonPropertyName("lookback_hours")]
    public int LookbackHours { get; init; }

    [JsonPropertyName("trace_ids")]
    public List<string>? TraceIds { get; init; }

    [JsonPropertyName("agent_id")]
    public string? AgentId { get; init; }
}

internal sealed class WireTargetCompletionsDataSource
{
    [JsonPropertyName("type")]
    public string Type { get; init; } = "azure_ai_target_completions";

    [JsonPropertyName("target")]
    public required IDictionary<string, object> Target { get; init; }

    [JsonPropertyName("source")]
    public required WireFileContentSource Source { get; init; }
}

// -----------------------------------------------------------------------
// Small item payloads used inside WireItemWrapper
// -----------------------------------------------------------------------

internal sealed class WireResponseIdItem
{
    [JsonPropertyName("resp_id")]
    public required string RespId { get; init; }
}

internal sealed class WireQueryItem
{
    [JsonPropertyName("query")]
    public required string Query { get; init; }
}
