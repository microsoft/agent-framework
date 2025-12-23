// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

/// <summary>
/// Base class for all item parameters (input items for creating conversation items or response inputs).
/// Unlike ItemResource, ItemParam does not have an ID field - the server generates IDs upon creation.
/// </summary>
[JsonConverter(typeof(ItemParamConverter))]
internal abstract class ItemParam
{
    /// <summary>
    /// The type of the item.
    /// </summary>
    [JsonPropertyName("type")]
    public abstract string Type { get; }
}

/// <summary>
/// Base class for message item parameters.
/// </summary>
[JsonConverter(typeof(ResponsesMessageItemParamConverter))]
internal abstract class ResponsesMessageItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for message items.
    /// </summary>
    public const string ItemType = "message";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The role of the message sender.
    /// </summary>
    [JsonPropertyName("role")]
    public abstract ChatRole Role { get; }
}

/// <summary>
/// A user message item parameter.
/// </summary>
internal sealed class ResponsesUserMessageItemParam : ResponsesMessageItemParam
{
    /// <summary>
    /// The constant role type identifier for user messages.
    /// </summary>
    public const string RoleType = "user";

    /// <inheritdoc/>
    public override ChatRole Role => ChatRole.User;

    /// <summary>
    /// The content of the message. Can be a simple string or an array of content parts.
    /// </summary>
    [JsonPropertyName("content")]
    public required InputMessageContent Content { get; init; }
}

/// <summary>
/// An assistant message item parameter.
/// </summary>
internal sealed class ResponsesAssistantMessageItemParam : ResponsesMessageItemParam
{
    /// <summary>
    /// The constant role type identifier for assistant messages.
    /// </summary>
    public const string RoleType = "assistant";

    /// <inheritdoc/>
    public override ChatRole Role => ChatRole.Assistant;

    /// <summary>
    /// The content of the message. Can be a simple string or an array of content parts.
    /// </summary>
    [JsonPropertyName("content")]
    public required InputMessageContent Content { get; init; }
}

/// <summary>
/// A system message item parameter.
/// </summary>
internal sealed class ResponsesSystemMessageItemParam : ResponsesMessageItemParam
{
    /// <summary>
    /// The constant role type identifier for system messages.
    /// </summary>
    public const string RoleType = "system";

    /// <inheritdoc/>
    public override ChatRole Role => ChatRole.System;

    /// <summary>
    /// The content of the message. Can be a simple string or an array of content parts.
    /// </summary>
    [JsonPropertyName("content")]
    public required InputMessageContent Content { get; init; }
}

/// <summary>
/// A developer message item parameter.
/// </summary>
internal sealed class ResponsesDeveloperMessageItemParam : ResponsesMessageItemParam
{
    /// <summary>
    /// The constant role type identifier for developer messages.
    /// </summary>
    public const string RoleType = "developer";

    /// <inheritdoc/>
    public override ChatRole Role => new(RoleType);

    /// <summary>
    /// The content of the message. Can be a simple string or an array of content parts.
    /// </summary>
    [JsonPropertyName("content")]
    public required InputMessageContent Content { get; init; }
}

/// <summary>
/// A function tool call item parameter.
/// </summary>
internal sealed class FunctionToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for function call items.
    /// </summary>
    public const string ItemType = "function_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The call ID of the function.
    /// </summary>
    [JsonPropertyName("call_id")]
    public required string CallId { get; init; }

    /// <summary>
    /// The name of the function.
    /// </summary>
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    /// <summary>
    /// The arguments to the function.
    /// </summary>
    [JsonPropertyName("arguments")]
    public required string Arguments { get; init; }
}

/// <summary>
/// A function tool call output item parameter.
/// </summary>
internal sealed class FunctionToolCallOutputItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for function call output items.
    /// </summary>
    public const string ItemType = "function_call_output";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The call ID of the function.
    /// </summary>
    [JsonPropertyName("call_id")]
    public required string CallId { get; init; }

    /// <summary>
    /// The output of the function.
    /// </summary>
    [JsonPropertyName("output")]
    public required string Output { get; init; }
}

/// <summary>
/// A file search tool call item parameter.
/// </summary>
internal sealed class FileSearchToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for file search call items.
    /// </summary>
    public const string ItemType = "file_search_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The queries used to search for files.
    /// </summary>
    [JsonPropertyName("queries")]
    public List<string>? Queries { get; init; }

    /// <summary>
    /// The results of the file search tool call.
    /// </summary>
    [JsonPropertyName("results")]
    public List<JsonElement>? Results { get; init; }
}

/// <summary>
/// A computer tool call item parameter.
/// </summary>
internal sealed class ComputerToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for computer call items.
    /// </summary>
    public const string ItemType = "computer_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// An identifier used when responding to the tool call with output.
    /// </summary>
    [JsonPropertyName("call_id")]
    public required string CallId { get; init; }

    /// <summary>
    /// The action to perform.
    /// </summary>
    [JsonPropertyName("action")]
    public required JsonElement Action { get; init; }

    /// <summary>
    /// The pending safety checks for the computer call.
    /// </summary>
    [JsonPropertyName("pending_safety_checks")]
    public List<JsonElement>? PendingSafetyChecks { get; init; }
}

/// <summary>
/// A computer tool call output item parameter.
/// </summary>
internal sealed class ComputerToolCallOutputItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for computer call output items.
    /// </summary>
    public const string ItemType = "computer_call_output";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The ID of the computer tool call that produced the output.
    /// </summary>
    [JsonPropertyName("call_id")]
    public required string CallId { get; init; }

    /// <summary>
    /// The safety checks reported by the API that have been acknowledged by the developer.
    /// </summary>
    [JsonPropertyName("acknowledged_safety_checks")]
    public List<JsonElement>? AcknowledgedSafetyChecks { get; init; }

    /// <summary>
    /// The output of the computer tool call.
    /// </summary>
    [JsonPropertyName("output")]
    public required JsonElement Output { get; init; }
}

/// <summary>
/// A web search tool call item parameter.
/// </summary>
internal sealed class WebSearchToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for web search call items.
    /// </summary>
    public const string ItemType = "web_search_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// An object describing the specific action taken in this web search call.
    /// </summary>
    [JsonPropertyName("action")]
    public required JsonElement Action { get; init; }
}

/// <summary>
/// A reasoning item parameter.
/// </summary>
internal sealed class ReasoningItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for reasoning items.
    /// </summary>
    public const string ItemType = "reasoning";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The encrypted content of the reasoning item.
    /// </summary>
    [JsonPropertyName("encrypted_content")]
    public string? EncryptedContent { get; init; }

    /// <summary>
    /// Reasoning text contents.
    /// </summary>
    [JsonPropertyName("summary")]
    public List<JsonElement>? Summary { get; init; }
}

/// <summary>
/// An item reference item parameter.
/// </summary>
internal sealed class ItemReferenceItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for item reference items.
    /// </summary>
    public const string ItemType = "item_reference";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The service-originated ID of the previously generated response item being referenced.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }
}

/// <summary>
/// An image generation tool call item parameter.
/// </summary>
internal sealed class ImageGenerationToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for image generation call items.
    /// </summary>
    public const string ItemType = "image_generation_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The generated image encoded in base64.
    /// </summary>
    [JsonPropertyName("result")]
    public string? Result { get; init; }
}

/// <summary>
/// A code interpreter tool call item parameter.
/// </summary>
internal sealed class CodeInterpreterToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for code interpreter call items.
    /// </summary>
    public const string ItemType = "code_interpreter_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The ID of the container used to run the code.
    /// </summary>
    [JsonPropertyName("container_id")]
    public string? ContainerId { get; init; }

    /// <summary>
    /// The code to run, or null if not available.
    /// </summary>
    [JsonPropertyName("code")]
    public string? Code { get; init; }

    /// <summary>
    /// The outputs generated by the code interpreter, such as logs or images.
    /// Can be null if no outputs are available.
    /// </summary>
    [JsonPropertyName("outputs")]
    public List<JsonElement>? Outputs { get; init; }
}

/// <summary>
/// A local shell tool call item parameter.
/// </summary>
internal sealed class LocalShellToolCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for local shell call items.
    /// </summary>
    public const string ItemType = "local_shell_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The unique ID of the local shell tool call generated by the model.
    /// </summary>
    [JsonPropertyName("call_id")]
    public string? CallId { get; init; }

    /// <summary>
    /// The action to execute.
    /// </summary>
    [JsonPropertyName("action")]
    public JsonElement? Action { get; init; }
}

/// <summary>
/// A local shell tool call output item parameter.
/// </summary>
internal sealed class LocalShellToolCallOutputItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for local shell call output items.
    /// </summary>
    public const string ItemType = "local_shell_call_output";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// A JSON string of the output of the local shell tool call.
    /// </summary>
    [JsonPropertyName("output")]
    public string? Output { get; init; }
}

/// <summary>
/// An MCP list tools item parameter.
/// </summary>
internal sealed class MCPListToolsItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for MCP list tools items.
    /// </summary>
    public const string ItemType = "mcp_list_tools";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The label of the MCP server.
    /// </summary>
    [JsonPropertyName("server_label")]
    public string? ServerLabel { get; init; }

    /// <summary>
    /// The tools available on the server.
    /// </summary>
    [JsonPropertyName("tools")]
    public List<JsonElement>? Tools { get; init; }

    /// <summary>
    /// Error message if the server could not list tools.
    /// </summary>
    [JsonPropertyName("error")]
    public string? Error { get; init; }
}

/// <summary>
/// An MCP approval request item parameter.
/// </summary>
internal sealed class MCPApprovalRequestItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for MCP approval request items.
    /// </summary>
    public const string ItemType = "mcp_approval_request";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The label of the MCP server making the request.
    /// </summary>
    [JsonPropertyName("server_label")]
    public string? ServerLabel { get; init; }

    /// <summary>
    /// The name of the tool to run.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    /// <summary>
    /// A JSON string of arguments for the tool.
    /// </summary>
    [JsonPropertyName("arguments")]
    public string? Arguments { get; init; }
}

/// <summary>
/// An MCP approval response item parameter.
/// </summary>
internal sealed class MCPApprovalResponseItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for MCP approval response items.
    /// </summary>
    public const string ItemType = "mcp_approval_response";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The ID of the approval request being answered.
    /// </summary>
    [JsonPropertyName("approval_request_id")]
    public string? ApprovalRequestId { get; init; }

    /// <summary>
    /// Whether the request was approved.
    /// </summary>
    [JsonPropertyName("approve")]
    public bool? Approve { get; init; }

    /// <summary>
    /// Optional reason for the decision.
    /// </summary>
    [JsonPropertyName("reason")]
    public string? Reason { get; init; }
}

/// <summary>
/// An MCP call item parameter.
/// </summary>
internal sealed class MCPCallItemParam : ItemParam
{
    /// <summary>
    /// The constant item type identifier for MCP call items.
    /// </summary>
    public const string ItemType = "mcp_call";

    /// <inheritdoc/>
    public override string Type => ItemType;

    /// <summary>
    /// The label of the MCP server running the tool.
    /// </summary>
    [JsonPropertyName("server_label")]
    public string? ServerLabel { get; init; }

    /// <summary>
    /// The name of the tool that was run.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; init; }

    /// <summary>
    /// A JSON string of the arguments passed to the tool.
    /// </summary>
    [JsonPropertyName("arguments")]
    public string? Arguments { get; init; }

    /// <summary>
    /// The output from the tool call.
    /// </summary>
    [JsonPropertyName("output")]
    public string? Output { get; init; }

    /// <summary>
    /// The error from the tool call, if any.
    /// </summary>
    [JsonPropertyName("error")]
    public string? Error { get; init; }
}
