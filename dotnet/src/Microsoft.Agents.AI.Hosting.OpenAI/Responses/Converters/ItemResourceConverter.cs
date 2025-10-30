// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ItemResource that handles type discrimination.
/// </summary>
[ExcludeFromCodeCoverage]
internal sealed class ItemResourceConverter : JsonConverter<ItemResource>
{
    private readonly ResponsesJsonContext _context;

    /// <summary>
    /// Initializes a new instance of the <see cref="ItemResourceConverter"/> class.
    /// </summary>
    public ItemResourceConverter()
    {
        this._context = ResponsesJsonContext.Default;
    }

    public override ItemResource? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        // Clone the reader to peek at the JSON
        Utf8JsonReader readerClone = reader;

        // Read through the JSON to find the type property
        string? type = null;

        if (readerClone.TokenType != JsonTokenType.StartObject)
        {
            throw new JsonException("Expected start of object");
        }

        while (readerClone.Read())
        {
            if (readerClone.TokenType == JsonTokenType.EndObject)
            {
                break;
            }

            if (readerClone.TokenType == JsonTokenType.PropertyName)
            {
                string propertyName = readerClone.GetString()!;
                readerClone.Read(); // Move to the value

                if (propertyName == "type")
                {
                    type = readerClone.GetString();
                    break;
                }

                if (readerClone.TokenType is JsonTokenType.StartObject or JsonTokenType.StartArray)
                {
                    // Skip nested objects/arrays
                    readerClone.Skip();
                }
            }
        }

        // Determine the concrete type based on the type discriminator and deserialize using the source generation context
        return type switch
        {
            ResponsesMessageItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ResponsesMessageItemResource),
            FileSearchToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.FileSearchToolCallItemResource),
            FunctionToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.FunctionToolCallItemResource),
            FunctionToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.FunctionToolCallOutputItemResource),
            ComputerToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ComputerToolCallItemResource),
            ComputerToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ComputerToolCallOutputItemResource),
            WebSearchToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.WebSearchToolCallItemResource),
            ReasoningItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ReasoningItemResource),
            ItemReferenceItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ItemReferenceItemResource),
            ImageGenerationToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.ImageGenerationToolCallItemResource),
            CodeInterpreterToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.CodeInterpreterToolCallItemResource),
            LocalShellToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.LocalShellToolCallItemResource),
            LocalShellToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.LocalShellToolCallOutputItemResource),
            MCPListToolsItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.MCPListToolsItemResource),
            MCPApprovalRequestItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.MCPApprovalRequestItemResource),
            MCPApprovalResponseItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.MCPApprovalResponseItemResource),
            MCPCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, this._context.MCPCallItemResource),
            _ => throw new JsonException($"Unknown item type: {type}")
        };
    }

    public override void Write(Utf8JsonWriter writer, ItemResource value, JsonSerializerOptions options)
    {
        // Directly serialize using the appropriate type info from the context
        switch (value)
        {
            case ResponsesMessageItemResource message:
                JsonSerializer.Serialize(writer, message, this._context.ResponsesMessageItemResource);
                break;
            case FileSearchToolCallItemResource fileSearch:
                JsonSerializer.Serialize(writer, fileSearch, this._context.FileSearchToolCallItemResource);
                break;
            case FunctionToolCallItemResource functionCall:
                JsonSerializer.Serialize(writer, functionCall, this._context.FunctionToolCallItemResource);
                break;
            case FunctionToolCallOutputItemResource functionOutput:
                JsonSerializer.Serialize(writer, functionOutput, this._context.FunctionToolCallOutputItemResource);
                break;
            case ComputerToolCallItemResource computerCall:
                JsonSerializer.Serialize(writer, computerCall, this._context.ComputerToolCallItemResource);
                break;
            case ComputerToolCallOutputItemResource computerOutput:
                JsonSerializer.Serialize(writer, computerOutput, this._context.ComputerToolCallOutputItemResource);
                break;
            case WebSearchToolCallItemResource webSearch:
                JsonSerializer.Serialize(writer, webSearch, this._context.WebSearchToolCallItemResource);
                break;
            case ReasoningItemResource reasoning:
                JsonSerializer.Serialize(writer, reasoning, this._context.ReasoningItemResource);
                break;
            case ItemReferenceItemResource itemReference:
                JsonSerializer.Serialize(writer, itemReference, this._context.ItemReferenceItemResource);
                break;
            case ImageGenerationToolCallItemResource imageGeneration:
                JsonSerializer.Serialize(writer, imageGeneration, this._context.ImageGenerationToolCallItemResource);
                break;
            case CodeInterpreterToolCallItemResource codeInterpreter:
                JsonSerializer.Serialize(writer, codeInterpreter, this._context.CodeInterpreterToolCallItemResource);
                break;
            case LocalShellToolCallItemResource localShell:
                JsonSerializer.Serialize(writer, localShell, this._context.LocalShellToolCallItemResource);
                break;
            case LocalShellToolCallOutputItemResource localShellOutput:
                JsonSerializer.Serialize(writer, localShellOutput, this._context.LocalShellToolCallOutputItemResource);
                break;
            case MCPListToolsItemResource mcpListTools:
                JsonSerializer.Serialize(writer, mcpListTools, this._context.MCPListToolsItemResource);
                break;
            case MCPApprovalRequestItemResource mcpApprovalRequest:
                JsonSerializer.Serialize(writer, mcpApprovalRequest, this._context.MCPApprovalRequestItemResource);
                break;
            case MCPApprovalResponseItemResource mcpApprovalResponse:
                JsonSerializer.Serialize(writer, mcpApprovalResponse, this._context.MCPApprovalResponseItemResource);
                break;
            case MCPCallItemResource mcpCall:
                JsonSerializer.Serialize(writer, mcpCall, this._context.MCPCallItemResource);
                break;
            default:
                throw new JsonException($"Unknown item type: {value.GetType().Name}");
        }
    }
}
