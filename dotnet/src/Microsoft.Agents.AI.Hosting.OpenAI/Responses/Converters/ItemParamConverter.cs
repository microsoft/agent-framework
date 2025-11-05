// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ItemParam that handles polymorphic deserialization based on the "type" discriminator.
/// </summary>
internal sealed class ItemParamConverter : JsonConverter<ItemParam>
{
    public override ItemParam? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var root = doc.RootElement;

        if (!root.TryGetProperty("type", out var typeElement))
        {
            throw new JsonException("ItemParam must have a 'type' property");
        }

        var type = typeElement.GetString();

        // Use OpenAIJsonContext directly since it has all the ItemParam type metadata
        return type switch
        {
            "message" => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesMessageItemParam),
            "function_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.FunctionToolCallItemParam),
            "function_call_output" => doc.Deserialize(OpenAIHostingJsonContext.Default.FunctionToolCallOutputItemParam),
            "file_search_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.FileSearchToolCallItemParam),
            "computer_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.ComputerToolCallItemParam),
            "computer_call_output" => doc.Deserialize(OpenAIHostingJsonContext.Default.ComputerToolCallOutputItemParam),
            "web_search_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.WebSearchToolCallItemParam),
            "reasoning" => doc.Deserialize(OpenAIHostingJsonContext.Default.ReasoningItemParam),
            "item_reference" => doc.Deserialize(OpenAIHostingJsonContext.Default.ItemReferenceItemParam),
            "image_generation_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.ImageGenerationToolCallItemParam),
            "code_interpreter_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.CodeInterpreterToolCallItemParam),
            "local_shell_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.LocalShellToolCallItemParam),
            "local_shell_call_output" => doc.Deserialize(OpenAIHostingJsonContext.Default.LocalShellToolCallOutputItemParam),
            "mcp_list_tools" => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPListToolsItemParam),
            "mcp_approval_request" => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPApprovalRequestItemParam),
            "mcp_approval_response" => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPApprovalResponseItemParam),
            "mcp_call" => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPCallItemParam),
            _ => null // Ignore unknown types.
        };
    }

    public override void Write(Utf8JsonWriter writer, ItemParam value, JsonSerializerOptions options)
    {
        // Use OpenAIJsonContext directly to serialize the concrete type
        JsonSerializer.Serialize(writer, value, OpenAIHostingJsonContext.Default.Options.GetTypeInfo(value.GetType()));
    }
}
