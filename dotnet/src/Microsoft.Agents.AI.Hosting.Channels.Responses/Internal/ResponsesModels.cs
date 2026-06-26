// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>Inbound OpenAI Responses request body (subset).</summary>
internal sealed class ResponsesRequestModel
{
    [JsonPropertyName("input")] public JsonElement? Input { get; set; }
    [JsonPropertyName("stream")] public bool Stream { get; set; }
    [JsonPropertyName("previous_response_id")] public string? PreviousResponseId { get; set; }
    [JsonPropertyName("model")] public string? Model { get; set; }
    [JsonPropertyName("instructions")] public string? Instructions { get; set; }
    [JsonPropertyName("metadata")] public Dictionary<string, object?>? Metadata { get; set; }

    // Generation-control fields remapped onto ChatOptions (stripped by the default run hook).
    [JsonPropertyName("temperature")] public double? Temperature { get; set; }
    [JsonPropertyName("top_p")] public double? TopP { get; set; }
    [JsonPropertyName("max_output_tokens")] public int? MaxOutputTokens { get; set; }
    [JsonPropertyName("parallel_tool_calls")] public bool? ParallelToolCalls { get; set; }

    // Caller identity: OpenAI Responses replaced `user` with `safety_identifier`. A non-string value is
    // tolerated and ignored (identity becomes null) rather than rejecting the request.
    [JsonPropertyName("safety_identifier")][JsonConverter(typeof(LenientStringConverter))] public string? SafetyIdentifier { get; set; }
    [JsonPropertyName("user")][JsonConverter(typeof(LenientStringConverter))] public string? User { get; set; }
}

/// <summary>Outbound Responses object (non-streaming + terminal stream payload).</summary>
internal sealed class ResponsesResponseModel
{
    [JsonPropertyName("id")] public string Id { get; set; } = string.Empty;
    [JsonPropertyName("object")] public string Object { get; set; } = "response";
    [JsonPropertyName("created_at")] public long CreatedAt { get; set; }
    [JsonPropertyName("status")] public string Status { get; set; } = "completed";
    [JsonPropertyName("model")] public string? Model { get; set; }
    [JsonPropertyName("output")] public List<ResponsesOutputItem> Output { get; set; } = [];
    [JsonPropertyName("usage")] public ResponsesUsageModel? Usage { get; set; }
    [JsonPropertyName("error")] public ResponsesErrorBody? Error { get; set; }
}

/// <summary>
/// Unified Responses output item. The <c>type</c> discriminates which fields apply: <c>message</c>
/// (role/content), <c>function_call</c> (call_id/name/arguments), <c>function_call_output</c>
/// (call_id/output), <c>reasoning</c> (summary/content), <c>mcp_call</c> (server_label/name/arguments/output),
/// <c>code_interpreter_call</c> (code/container_id/outputs), <c>image_generation_call</c> (result),
/// <c>mcp_approval_request</c> (server_label/name/arguments) or <c>mcp_approval_response</c>
/// (approval_request_id/approve). Unset fields are omitted when serialized. Shape-varying fields
/// (<c>content</c>, <c>output</c>, <c>summary</c>, <c>outputs</c>) are modeled as <see cref="JsonNode"/> so a
/// single item type can carry the exact OpenAI Responses shape for each content kind.
/// </summary>
[JsonConverter(typeof(ResponsesOutputItemConverter))]
internal sealed class ResponsesOutputItem
{
    [JsonPropertyName("type")] public string Type { get; set; } = "message";
    [JsonPropertyName("id")] public string Id { get; set; } = string.Empty;
    [JsonPropertyName("status")] public string? Status { get; set; }

    // message (output_text[]) / reasoning (reasoning_text[])
    [JsonPropertyName("role")] public string? Role { get; set; }
    [JsonPropertyName("content")] public JsonNode? Content { get; set; }

    // function_call / function_call_output / mcp_call / mcp_approval_request
    [JsonPropertyName("call_id")] public string? CallId { get; set; }
    [JsonPropertyName("name")] public string? Name { get; set; }
    [JsonPropertyName("arguments")] public string? Arguments { get; set; }

    // function_call_output (string or input-part[]) / mcp_call (string)
    [JsonPropertyName("output")] public JsonNode? Output { get; set; }

    // reasoning
    [JsonPropertyName("summary")] public JsonNode? Summary { get; set; }
    [JsonPropertyName("encrypted_content")] public string? EncryptedContent { get; set; }

    // mcp_call / mcp_approval_request
    [JsonPropertyName("server_label")] public string? ServerLabel { get; set; }

    // code_interpreter_call
    [JsonPropertyName("code")] public string? Code { get; set; }
    [JsonPropertyName("container_id")] public string? ContainerId { get; set; }
    [JsonPropertyName("outputs")] public JsonNode? Outputs { get; set; }

    // image_generation_call
    [JsonPropertyName("result")] public string? Result { get; set; }

    // mcp_approval_response
    [JsonPropertyName("approval_request_id")] public string? ApprovalRequestId { get; set; }
    [JsonPropertyName("approve")] public bool? Approve { get; set; }

    /// <summary>When set, the item is a raw provider Responses output item and is written verbatim.</summary>
    [JsonIgnore] public JsonObject? RawItem { get; set; }
}

internal sealed class ResponsesOutputText
{
    [JsonPropertyName("type")] public string Type { get; set; } = "output_text";
    [JsonPropertyName("text")] public string Text { get; set; } = string.Empty;
    [JsonPropertyName("annotations")] public List<object> Annotations { get; set; } = [];
}

internal sealed class ResponsesUsageModel
{
    [JsonPropertyName("input_tokens")] public int InputTokens { get; set; }
    [JsonPropertyName("output_tokens")] public int OutputTokens { get; set; }
    [JsonPropertyName("total_tokens")] public int TotalTokens { get; set; }
}

/// <summary>SSE payload for response.created / response.completed / response.failed.</summary>
internal sealed class ResponsesStreamResponseEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = string.Empty;
    [JsonPropertyName("response")] public ResponsesResponseModel Response { get; set; } = new();
}

/// <summary>SSE payload for response.output_item.added / response.output_item.done.</summary>
internal sealed class ResponsesStreamOutputItemEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("item")] public ResponsesOutputItem Item { get; set; } = new();
}

/// <summary>SSE payload for response.content_part.added / response.content_part.done.</summary>
internal sealed class ResponsesStreamContentPartEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = string.Empty;
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("content_index")] public int ContentIndex { get; set; }
    [JsonPropertyName("part")] public ResponsesOutputText Part { get; set; } = new();
}

/// <summary>SSE payload for response.output_text.delta.</summary>
internal sealed class ResponsesStreamTextDeltaEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.output_text.delta";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("content_index")] public int ContentIndex { get; set; }
    [JsonPropertyName("delta")] public string Delta { get; set; } = string.Empty;
}

/// <summary>SSE payload for response.output_text.done.</summary>
internal sealed class ResponsesStreamTextDoneEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.output_text.done";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("content_index")] public int ContentIndex { get; set; }
    [JsonPropertyName("text")] public string Text { get; set; } = string.Empty;
}

/// <summary>SSE payload for response.reasoning_text.delta.</summary>
internal sealed class ResponsesStreamReasoningTextDeltaEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.reasoning_text.delta";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("content_index")] public int ContentIndex { get; set; }
    [JsonPropertyName("delta")] public string Delta { get; set; } = string.Empty;
}

/// <summary>SSE payload for response.reasoning_text.done.</summary>
internal sealed class ResponsesStreamReasoningTextDoneEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.reasoning_text.done";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("content_index")] public int ContentIndex { get; set; }
    [JsonPropertyName("text")] public string Text { get; set; } = string.Empty;
}

/// <summary>SSE payload for response.function_call_arguments.delta.</summary>
internal sealed class ResponsesStreamFunctionCallArgumentsDeltaEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.function_call_arguments.delta";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("delta")] public string Delta { get; set; } = string.Empty;
}

/// <summary>SSE payload for response.function_call_arguments.done.</summary>
internal sealed class ResponsesStreamFunctionCallArgumentsDoneEvent
{
    [JsonPropertyName("type")] public string Type { get; set; } = "response.function_call_arguments.done";
    [JsonPropertyName("item_id")] public string ItemId { get; set; } = string.Empty;
    [JsonPropertyName("output_index")] public int OutputIndex { get; set; }
    [JsonPropertyName("arguments")] public string Arguments { get; set; } = string.Empty;
    [JsonPropertyName("name")] public string? Name { get; set; }
}

/// <summary>Error envelope.</summary>
internal sealed class ResponsesErrorModel
{
    [JsonPropertyName("error")] public ResponsesErrorBody Error { get; set; } = new();
}

internal sealed class ResponsesErrorBody
{
    [JsonPropertyName("type")] public string Type { get; set; } = "invalid_request_error";
    [JsonPropertyName("message")] public string? Message { get; set; }
}
