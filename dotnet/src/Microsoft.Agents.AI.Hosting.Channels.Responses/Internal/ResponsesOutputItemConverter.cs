// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Serializes a <see cref="ResponsesOutputItem"/>. When <see cref="ResponsesOutputItem.RawItem"/> is set the
/// raw provider node is written verbatim (raw-item passthrough); otherwise the type-discriminated fields are
/// written, omitting nulls so each <c>type</c> carries only its applicable keys.
/// </summary>
internal sealed class ResponsesOutputItemConverter : JsonConverter<ResponsesOutputItem>
{
    public override ResponsesOutputItem Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var node = JsonNode.Parse(ref reader);
        return new ResponsesOutputItem
        {
            RawItem = node as JsonObject,
            Type = node?["type"]?.GetValue<string>() ?? "message",
            Id = node?["id"]?.GetValue<string>() ?? string.Empty,
        };
    }

    public override void Write(Utf8JsonWriter writer, ResponsesOutputItem value, JsonSerializerOptions options)
    {
        if (value.RawItem is not null)
        {
            value.RawItem.WriteTo(writer, options);
            return;
        }

        writer.WriteStartObject();
        writer.WriteString("type", value.Type);
        writer.WriteString("id", value.Id);
        WriteOptionalString(writer, "status", value.Status);
        WriteOptionalString(writer, "role", value.Role);
        WriteOptionalNode(writer, "content", value.Content, options);
        WriteOptionalString(writer, "call_id", value.CallId);
        WriteOptionalString(writer, "name", value.Name);
        WriteOptionalString(writer, "arguments", value.Arguments);
        WriteOptionalNode(writer, "output", value.Output, options);
        WriteOptionalNode(writer, "summary", value.Summary, options);
        WriteOptionalString(writer, "encrypted_content", value.EncryptedContent);
        WriteOptionalString(writer, "server_label", value.ServerLabel);
        WriteOptionalString(writer, "code", value.Code);
        WriteOptionalString(writer, "container_id", value.ContainerId);
        WriteOptionalNode(writer, "outputs", value.Outputs, options);
        WriteOptionalString(writer, "result", value.Result);
        WriteOptionalString(writer, "approval_request_id", value.ApprovalRequestId);
        if (value.Approve is { } approve)
        {
            writer.WriteBoolean("approve", approve);
        }

        writer.WriteEndObject();
    }

    private static void WriteOptionalString(Utf8JsonWriter writer, string name, string? value)
    {
        if (value is not null)
        {
            writer.WriteString(name, value);
        }
    }

    private static void WriteOptionalNode(Utf8JsonWriter writer, string name, JsonNode? value, JsonSerializerOptions options)
    {
        if (value is not null)
        {
            writer.WritePropertyName(name);
            value.WriteTo(writer, options);
        }
    }
}
