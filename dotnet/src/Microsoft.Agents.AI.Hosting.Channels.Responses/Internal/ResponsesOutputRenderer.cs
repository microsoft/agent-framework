// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Renders a flat sequence of <see cref="AIContent"/> into OpenAI Responses output items, mirroring the Python
/// <c>_contents_to_output_items</c> flow: per content-type projection, call/result coalescing (image generation,
/// MCP, code interpreter), raw-item passthrough/replacement, and media projection into input-content parts.
/// </summary>
internal static class ResponsesOutputRenderer
{
    public static List<ResponsesOutputItem> Render(IReadOnlyList<AIContent> contents, string status)
    {
        var items = new List<ResponsesOutputItem>();
        var seenRaw = new Dictionary<(string Type, string Id), int>();
        List<JsonNode>? messageContent = null;

        void FlushMessage()
        {
            if (messageContent is { Count: > 0 })
            {
                items.Add(BuildMessage(messageContent, status, id: null));
                messageContent = null;
            }
        }

        for (var index = 0; index < contents.Count; index++)
        {
            var content = contents[index];

            var raw = TryRawItem(content);
            if (raw is not null)
            {
                var key = RawItemKey(raw);
                if (key is { } k && seenRaw.TryGetValue(k, out var existing))
                {
                    items[existing] = new ResponsesOutputItem { Type = raw["type"]!.GetValue<string>(), Id = raw["id"]?.GetValue<string>() ?? string.Empty, RawItem = raw };
                }
                else
                {
                    FlushMessage();
                    if (key is { } nk)
                    {
                        seenRaw[nk] = items.Count;
                    }

                    items.Add(new ResponsesOutputItem { Type = raw["type"]!.GetValue<string>(), Id = raw["id"]?.GetValue<string>() ?? string.Empty, RawItem = raw });
                }

                continue;
            }

            var next = index + 1 < contents.Count ? contents[index + 1] : null;

            if (content is CodeInterpreterToolCallContent ciCall && next is CodeInterpreterToolResultContent ciResult && ciCall.CallId == ciResult.CallId)
            {
                FlushMessage();
                items.Add(CodeInterpreterItem(ciCall, ciResult, status));
                index++;
                continue;
            }

            if (content is ImageGenerationToolCallContent igCall && next is ImageGenerationToolResultContent igResult && igCall.CallId == igResult.CallId)
            {
                FlushMessage();
                items.Add(ImageGenerationItem(igCall, igResult, status));
                index++;
                continue;
            }

            if (content is McpServerToolCallContent mcpCall && next is McpServerToolResultContent mcpResult && mcpCall.CallId == mcpResult.CallId)
            {
                FlushMessage();
                items.Add(McpCallItem(mcpCall, mcpResult, status));
                index++;
                continue;
            }

            switch (content)
            {
                case TextContent text:
                    (messageContent ??= []).Add(OutputTextNode(text.Text ?? string.Empty));
                    break;
                case ErrorContent error:
                    (messageContent ??= []).Add(OutputTextNode(error.Message ?? error.ToString() ?? string.Empty));
                    break;
                case TextReasoningContent reasoning:
                    FlushMessage();
                    items.Add(ReasoningItem(reasoning, status));
                    break;
                case FunctionCallContent call:
                    FlushMessage();
                    items.Add(FunctionCallItem(call, status));
                    break;
                case FunctionResultContent result:
                    FlushMessage();
                    items.Add(FunctionResultItem(result, status));
                    break;
                case CodeInterpreterToolCallContent ci:
                    FlushMessage();
                    items.Add(CodeInterpreterItem(ci, null, status));
                    break;
                case CodeInterpreterToolResultContent ciOnly:
                    FlushMessage();
                    items.Add(CodeInterpreterItem(null, ciOnly, status));
                    break;
                case ImageGenerationToolCallContent ig:
                    FlushMessage();
                    items.Add(ImageGenerationItem(ig, null, status));
                    break;
                case ImageGenerationToolResultContent igOnly:
                    FlushMessage();
                    items.Add(ImageGenerationItem(null, igOnly, status));
                    break;
                case McpServerToolCallContent mcp:
                    FlushMessage();
                    items.Add(McpCallItem(mcp, null, status));
                    break;
                case McpServerToolResultContent mcpResultOnly:
                    FlushMessage();
                    items.Add(McpResultItem(mcpResultOnly, status));
                    break;
                case ToolApprovalRequestContent approvalRequest:
                    FlushMessage();
                    items.Add(ApprovalRequestItem(approvalRequest));
                    break;
                case ToolApprovalResponseContent approvalResponse:
                    FlushMessage();
                    items.Add(ApprovalResponseItem(approvalResponse));
                    break;
                case DataContent or UriContent or HostedFileContent:
                    FlushMessage();
                    items.Add(MediaItem(content, status));
                    break;
                default:
                    var fallback = content.ToString();
                    if (!string.IsNullOrEmpty(fallback))
                    {
                        (messageContent ??= []).Add(OutputTextNode(fallback));
                    }

                    break;
            }
        }

        FlushMessage();
        return items;
    }

    private static string MessageStatus(string status) =>
        status is "in_progress" or "completed" or "incomplete" ? status : "incomplete";

    private static JsonObject OutputTextNode(string text) =>
        new() { ["type"] = "output_text", ["text"] = text, ["annotations"] = new JsonArray() };

    private static JsonArray Append(JsonArray array, JsonNode node)
    {
        array.Add(node);
        return array;
    }

    private static ResponsesOutputItem BuildMessage(List<JsonNode> content, string status, string? id)
    {
        var array = new JsonArray();
        foreach (var node in content)
        {
            Append(array, node);
        }

        return new ResponsesOutputItem
        {
            Type = "message",
            Id = id ?? "msg_" + Guid.NewGuid().ToString("N"),
            Role = "assistant",
            Status = MessageStatus(status),
            Content = array,
        };
    }

    private static ResponsesOutputItem ReasoningItem(TextReasoningContent reasoning, string status)
    {
        var text = reasoning.Text ?? string.Empty;
        var item = new ResponsesOutputItem
        {
            Type = "reasoning",
            Id = "rs_" + Guid.NewGuid().ToString("N"),
            Summary = new JsonArray(),
            Status = MessageStatus(status),
        };
        if (text.Length > 0)
        {
            item.Content = new JsonArray(new JsonObject { ["type"] = "reasoning_text", ["text"] = text });
        }

        if (!string.IsNullOrEmpty(reasoning.ProtectedData))
        {
            item.EncryptedContent = reasoning.ProtectedData;
        }

        return item;
    }

    private static ResponsesOutputItem FunctionCallItem(FunctionCallContent call, string status) => new()
    {
        Type = "function_call",
        Id = "fc_" + Guid.NewGuid().ToString("N"),
        CallId = call.CallId ?? "call_" + Guid.NewGuid().ToString("N"),
        Name = string.IsNullOrEmpty(call.Name) ? "tool" : call.Name,
        Arguments = SerializeArguments(call.Arguments),
        Status = MessageStatus(status),
    };

    private static ResponsesOutputItem FunctionResultItem(FunctionResultContent result, string status)
    {
        JsonNode output;
        if (result.Exception is { } ex)
        {
            output = JsonValue.Create(ex.Message)!;
        }
        else if (ContentPartsToInputItems(AsContentList(result.Result)) is { Count: > 0 } parts)
        {
            output = parts;
        }
        else if (result.Result is string s)
        {
            output = JsonValue.Create(s)!;
        }
        else if (result.Result is null)
        {
            output = JsonValue.Create(string.Empty)!;
        }
        else
        {
            output = JsonValue.Create(result.Result.ToString() ?? string.Empty)!;
        }

        return new ResponsesOutputItem
        {
            Type = "function_call_output",
            Id = "fcout_" + Guid.NewGuid().ToString("N"),
            CallId = result.CallId ?? "call_" + Guid.NewGuid().ToString("N"),
            Output = output,
            Status = MessageStatus(status),
        };
    }

    private static ResponsesOutputItem MediaItem(AIContent content, string status)
    {
        var parts = ContentPartsToInputItems([content]);
        if (parts is { Count: > 0 })
        {
            return new ResponsesOutputItem
            {
                Type = "function_call_output",
                Id = "content_" + Guid.NewGuid().ToString("N"),
                CallId = "content_" + Guid.NewGuid().ToString("N"),
                Output = parts,
                Status = MessageStatus(status),
            };
        }

        return BuildMessage([OutputTextNode(content.ToString() ?? string.Empty)], status, id: null);
    }

    private static ResponsesOutputItem McpCallItem(McpServerToolCallContent call, McpServerToolResultContent? result, string status) => new()
    {
        Type = "mcp_call",
        Id = call.CallId ?? "mcp_" + Guid.NewGuid().ToString("N"),
        ServerLabel = string.IsNullOrEmpty(call.ServerName) ? "default" : call.ServerName,
        Name = string.IsNullOrEmpty(call.Name) ? "tool" : call.Name,
        Arguments = SerializeArguments(call.Arguments),
        Output = result is not null ? JsonValue.Create(StringifyOutputs(result.Outputs)) : null,
        Status = MessageStatus(status),
    };

    private static ResponsesOutputItem McpResultItem(McpServerToolResultContent result, string status) => new()
    {
        Type = "mcp_call",
        Id = result.CallId ?? "mcp_" + Guid.NewGuid().ToString("N"),
        ServerLabel = "default",
        Name = "tool",
        Arguments = string.Empty,
        Output = JsonValue.Create(StringifyOutputs(result.Outputs)),
        Status = MessageStatus(status),
    };

    private static ResponsesOutputItem CodeInterpreterItem(CodeInterpreterToolCallContent? call, CodeInterpreterToolResultContent? result, string status)
    {
        var code = call is not null ? ContentSequenceText(call.Inputs) : string.Empty;
        var outputsValue = result?.Outputs;
        JsonArray? outputs = null;
        if (outputsValue is not null)
        {
            foreach (var item in outputsValue)
            {
                switch (item)
                {
                    case TextContent t:
                        Append(outputs ??= [], new JsonObject { ["type"] = "logs", ["logs"] = t.Text ?? string.Empty });
                        break;
                    case UriContent u:
                        Append(outputs ??= [], new JsonObject { ["type"] = "image", ["url"] = u.Uri.ToString() });
                        break;
                    case DataContent d when !string.IsNullOrEmpty(d.Uri):
                        Append(outputs ??= [], new JsonObject { ["type"] = "image", ["url"] = d.Uri });
                        break;
                }
            }
        }

        return new ResponsesOutputItem
        {
            Type = "code_interpreter_call",
            Id = (call?.CallId ?? result?.CallId) ?? "ci_" + Guid.NewGuid().ToString("N"),
            Code = code,
            ContainerId = "agent_framework",
            Outputs = outputs,
            Status = MessageStatus(status),
        };
    }

    private static ResponsesOutputItem ImageGenerationItem(ImageGenerationToolCallContent? call, ImageGenerationToolResultContent? result, string status) => new()
    {
        Type = "image_generation_call",
        Id = (call?.CallId ?? result?.CallId) ?? "ig_" + Guid.NewGuid().ToString("N"),
        Result = ImageGenerationResult(result?.Outputs),
        Status = MessageStatus(status),
    };

    private static ResponsesOutputItem ApprovalRequestItem(ToolApprovalRequestContent content)
    {
        var (name, arguments, serverLabel) = DescribeToolCall(content.ToolCall);
        return new ResponsesOutputItem
        {
            Type = "mcp_approval_request",
            Id = string.IsNullOrEmpty(content.RequestId) ? "approval_" + Guid.NewGuid().ToString("N") : content.RequestId,
            ServerLabel = serverLabel,
            Name = name,
            Arguments = arguments,
        };
    }

    private static ResponsesOutputItem ApprovalResponseItem(ToolApprovalResponseContent content) => new()
    {
        Type = "mcp_approval_response",
        Id = string.IsNullOrEmpty(content.RequestId) ? "approval_" + Guid.NewGuid().ToString("N") : content.RequestId,
        ApprovalRequestId = content.RequestId ?? string.Empty,
        Approve = content.Approved,
    };

    private static (string Name, string Arguments, string ServerLabel) DescribeToolCall(ToolCallContent? toolCall)
    {
        switch (toolCall)
        {
            case McpServerToolCallContent mcp:
                return (string.IsNullOrEmpty(mcp.Name) ? "tool" : mcp.Name, SerializeArguments(mcp.Arguments), string.IsNullOrEmpty(mcp.ServerName) ? "agent_framework" : mcp.ServerName);
            case FunctionCallContent fn:
                var label = "agent_framework";
                if (fn.AdditionalProperties is { } props && props.TryGetValue("server_label", out var raw) && raw is string s && !string.IsNullOrEmpty(s))
                {
                    label = s;
                }

                return (string.IsNullOrEmpty(fn.Name) ? "tool" : fn.Name, SerializeArguments(fn.Arguments), label);
            default:
                return ("tool", string.Empty, "agent_framework");
        }
    }

    private static IReadOnlyList<AIContent> AsContentList(object? value) => value switch
    {
        IReadOnlyList<AIContent> list => list,
        IEnumerable<AIContent> seq => [.. seq],
        _ => [],
    };

    private static JsonArray? ContentPartsToInputItems(IReadOnlyList<AIContent> contents)
    {
        if (contents.Count == 0)
        {
            return null;
        }

        JsonArray? parts = null;
        foreach (var content in contents)
        {
            switch (content)
            {
                case TextContent text:
                    Append(parts ??= [], new JsonObject { ["type"] = "input_text", ["text"] = text.Text ?? string.Empty });
                    break;
                case UriContent uri:
                    AddMediaPart(ref parts, uri.Uri.ToString(), IsImage(uri.MediaType));
                    break;
                case DataContent data when !string.IsNullOrEmpty(data.Uri):
                    AddMediaPart(ref parts, data.Uri, IsImage(data.MediaType));
                    break;
                case HostedFileContent file when !string.IsNullOrEmpty(file.FileId):
                    Append(parts ??= [], new JsonObject { ["type"] = "input_file", ["file_id"] = file.FileId });
                    break;
            }
        }

        return parts;
    }

    private static void AddMediaPart(ref JsonArray? parts, string uri, bool isImage)
    {
        if (isImage)
        {
            Append(parts ??= [], new JsonObject { ["type"] = "input_image", ["image_url"] = uri, ["detail"] = "auto" });
        }
        else
        {
            Append(parts ??= [], new JsonObject { ["type"] = "input_file", ["file_url"] = uri });
        }
    }

    private static bool IsImage(string? mediaType) =>
        mediaType?.StartsWith("image/", StringComparison.OrdinalIgnoreCase) == true;

    private static string StringifyOutputs(IList<AIContent>? outputs)
    {
        if (outputs is null || outputs.Count == 0)
        {
            return string.Empty;
        }

        var sb = new StringBuilder();
        foreach (var content in outputs)
        {
            if (content is TextContent text)
            {
                sb.Append(text.Text);
            }
        }

        return sb.ToString();
    }

    private static string ContentSequenceText(IList<AIContent>? contents)
    {
        if (contents is null)
        {
            return string.Empty;
        }

        var sb = new StringBuilder();
        foreach (var content in contents)
        {
            if (content is TextContent text)
            {
                sb.Append(text.Text);
            }
        }

        return sb.ToString();
    }

    private static string ImageGenerationResult(IList<AIContent>? outputs)
    {
        if (outputs is null)
        {
            return string.Empty;
        }

        foreach (var content in outputs)
        {
            var uri = content switch
            {
                DataContent d => d.Uri,
                UriContent u => u.Uri.ToString(),
                _ => null,
            };
            if (uri is null)
            {
                continue;
            }

            var marker = uri.IndexOf("base64,", StringComparison.Ordinal);
            return marker >= 0 ? uri[(marker + "base64,".Length)..] : uri;
        }

        return string.Empty;
    }

    private static JsonObject? TryRawItem(AIContent content)
    {
        if (content.RawRepresentation is null)
        {
            return null;
        }

        JsonNode? node = content.RawRepresentation switch
        {
            JsonObject obj => obj.DeepClone(),
            JsonNode jn => jn.DeepClone(),
            JsonElement { ValueKind: JsonValueKind.Object } el => JsonNode.Parse(el.GetRawText()),
            _ => null,
        };

        if (node is JsonObject result && result.ContainsKey("type"))
        {
            return result;
        }

        return null;
    }

    private static (string Type, string Id)? RawItemKey(JsonObject raw)
    {
        if (raw["type"]?.GetValue<string>() is { } type && raw["id"]?.GetValue<string>() is { } id)
        {
            return (type, id);
        }

        return null;
    }

    internal static string SerializeArguments(IDictionary<string, object?>? arguments)
    {
        if (arguments is null || arguments.Count == 0)
        {
            return "{}";
        }

        var buffer = new System.Buffers.ArrayBufferWriter<byte>();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            foreach (var (key, value) in arguments)
            {
                writer.WritePropertyName(key);
                WriteArgumentValue(writer, value);
            }

            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(buffer.WrittenSpan);
    }

    private static void WriteArgumentValue(Utf8JsonWriter writer, object? value)
    {
        switch (value)
        {
            case null:
                writer.WriteNullValue();
                break;
            case string s:
                writer.WriteStringValue(s);
                break;
            case bool b:
                writer.WriteBooleanValue(b);
                break;
            case int i:
                writer.WriteNumberValue(i);
                break;
            case long l:
                writer.WriteNumberValue(l);
                break;
            case double d:
                writer.WriteNumberValue(d);
                break;
            case JsonElement el:
                el.WriteTo(writer);
                break;
            default:
                writer.WriteStringValue(Convert.ToString(value, CultureInfo.InvariantCulture));
                break;
        }
    }
}
