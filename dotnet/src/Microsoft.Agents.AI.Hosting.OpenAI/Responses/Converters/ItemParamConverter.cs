// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ItemParam that handles polymorphic deserialization based on the "type" discriminator.
/// </summary>
[ExcludeFromCodeCoverage]
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
        var jsonText = root.GetRawText();

        // Use OpenAIJsonContext directly since it has all the ItemParam type metadata
        return type switch
        {
            "message" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ResponsesMessageItemParam),
            "function_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.FunctionToolCallItemParam),
            "function_call_output" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.FunctionToolCallOutputItemParam),
            "file_search_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.FileSearchToolCallItemParam),
            "computer_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ComputerToolCallItemParam),
            "computer_call_output" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ComputerToolCallOutputItemParam),
            "web_search_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.WebSearchToolCallItemParam),
            "reasoning" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ReasoningItemParam),
            "item_reference" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ItemReferenceItemParam),
            "image_generation_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.ImageGenerationToolCallItemParam),
            "code_interpreter_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.CodeInterpreterToolCallItemParam),
            "local_shell_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.LocalShellToolCallItemParam),
            "local_shell_call_output" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.LocalShellToolCallOutputItemParam),
            "mcp_list_tools" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.MCPListToolsItemParam),
            "mcp_approval_request" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.MCPApprovalRequestItemParam),
            "mcp_approval_response" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.MCPApprovalResponseItemParam),
            "mcp_call" => JsonSerializer.Deserialize(jsonText, OpenAIHostingJsonContext.Default.MCPCallItemParam),
            _ => throw new JsonException($"Unknown ItemParam type: {type}")
        };
    }

    public override void Write(Utf8JsonWriter writer, ItemParam value, JsonSerializerOptions options)
    {
        // Use OpenAIJsonContext directly to serialize the concrete type
        JsonSerializer.Serialize(writer, value, OpenAIHostingJsonContext.Default.Options.GetTypeInfo(value.GetType()));
    }
}
