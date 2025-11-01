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
    /// <inheritdoc/>
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
                    // The Utf8JsonReader.Skip() method will fail fast if it detects that we're reading
                    // from a partially read buffer, regardless of whether the next value is available.
                    // This can result in erroneous failures in cases where a custom converter is calling
                    // into a built-in converter (cf. https://github.com/dotnet/runtime/issues/74108).
                    // For this reason we need to call the TrySkip() method instead -- the serializer
                    // should guarantee sufficient read-ahead has been performed for the current object.
                    if (!readerClone.TrySkip())
                    {
                        throw new InvalidOperationException("Failed to skip nested JSON value. Serializer should guarantee sufficient read-ahead has been done.");
                    }
                }
            }
        }

        // Determine the concrete type based on the type discriminator and deserialize using the source generation context
        return type switch
        {
            ResponsesMessageItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ResponsesMessageItemResource),
            FileSearchToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.FileSearchToolCallItemResource),
            FunctionToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.FunctionToolCallItemResource),
            FunctionToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.FunctionToolCallOutputItemResource),
            ComputerToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ComputerToolCallItemResource),
            ComputerToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ComputerToolCallOutputItemResource),
            WebSearchToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.WebSearchToolCallItemResource),
            ReasoningItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ReasoningItemResource),
            ItemReferenceItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ItemReferenceItemResource),
            ImageGenerationToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.ImageGenerationToolCallItemResource),
            CodeInterpreterToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.CodeInterpreterToolCallItemResource),
            LocalShellToolCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.LocalShellToolCallItemResource),
            LocalShellToolCallOutputItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.LocalShellToolCallOutputItemResource),
            MCPListToolsItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.MCPListToolsItemResource),
            MCPApprovalRequestItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.MCPApprovalRequestItemResource),
            MCPApprovalResponseItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.MCPApprovalResponseItemResource),
            MCPCallItemResource.ItemType => JsonSerializer.Deserialize(ref reader, OpenAIHostingJsonContext.Default.MCPCallItemResource),
            _ => throw new JsonException($"Unknown item type: {type}")
        };
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, ItemResource value, JsonSerializerOptions options)
    {
        // Directly serialize using the appropriate type info from the context
        switch (value)
        {
            case ResponsesMessageItemResource message:
                JsonSerializer.Serialize(writer, message, OpenAIHostingJsonContext.Default.ResponsesMessageItemResource);
                break;
            case FileSearchToolCallItemResource fileSearch:
                JsonSerializer.Serialize(writer, fileSearch, OpenAIHostingJsonContext.Default.FileSearchToolCallItemResource);
                break;
            case FunctionToolCallItemResource functionCall:
                JsonSerializer.Serialize(writer, functionCall, OpenAIHostingJsonContext.Default.FunctionToolCallItemResource);
                break;
            case FunctionToolCallOutputItemResource functionOutput:
                JsonSerializer.Serialize(writer, functionOutput, OpenAIHostingJsonContext.Default.FunctionToolCallOutputItemResource);
                break;
            case ComputerToolCallItemResource computerCall:
                JsonSerializer.Serialize(writer, computerCall, OpenAIHostingJsonContext.Default.ComputerToolCallItemResource);
                break;
            case ComputerToolCallOutputItemResource computerOutput:
                JsonSerializer.Serialize(writer, computerOutput, OpenAIHostingJsonContext.Default.ComputerToolCallOutputItemResource);
                break;
            case WebSearchToolCallItemResource webSearch:
                JsonSerializer.Serialize(writer, webSearch, OpenAIHostingJsonContext.Default.WebSearchToolCallItemResource);
                break;
            case ReasoningItemResource reasoning:
                JsonSerializer.Serialize(writer, reasoning, OpenAIHostingJsonContext.Default.ReasoningItemResource);
                break;
            case ItemReferenceItemResource itemReference:
                JsonSerializer.Serialize(writer, itemReference, OpenAIHostingJsonContext.Default.ItemReferenceItemResource);
                break;
            case ImageGenerationToolCallItemResource imageGeneration:
                JsonSerializer.Serialize(writer, imageGeneration, OpenAIHostingJsonContext.Default.ImageGenerationToolCallItemResource);
                break;
            case CodeInterpreterToolCallItemResource codeInterpreter:
                JsonSerializer.Serialize(writer, codeInterpreter, OpenAIHostingJsonContext.Default.CodeInterpreterToolCallItemResource);
                break;
            case LocalShellToolCallItemResource localShell:
                JsonSerializer.Serialize(writer, localShell, OpenAIHostingJsonContext.Default.LocalShellToolCallItemResource);
                break;
            case LocalShellToolCallOutputItemResource localShellOutput:
                JsonSerializer.Serialize(writer, localShellOutput, OpenAIHostingJsonContext.Default.LocalShellToolCallOutputItemResource);
                break;
            case MCPListToolsItemResource mcpListTools:
                JsonSerializer.Serialize(writer, mcpListTools, OpenAIHostingJsonContext.Default.MCPListToolsItemResource);
                break;
            case MCPApprovalRequestItemResource mcpApprovalRequest:
                JsonSerializer.Serialize(writer, mcpApprovalRequest, OpenAIHostingJsonContext.Default.MCPApprovalRequestItemResource);
                break;
            case MCPApprovalResponseItemResource mcpApprovalResponse:
                JsonSerializer.Serialize(writer, mcpApprovalResponse, OpenAIHostingJsonContext.Default.MCPApprovalResponseItemResource);
                break;
            case MCPCallItemResource mcpCall:
                JsonSerializer.Serialize(writer, mcpCall, OpenAIHostingJsonContext.Default.MCPCallItemResource);
                break;
            default:
                throw new JsonException($"Unknown item type: {value.GetType().Name}");
        }
    }
}
