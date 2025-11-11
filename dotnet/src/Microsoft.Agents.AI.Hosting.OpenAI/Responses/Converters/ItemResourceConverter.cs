// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// JSON converter for ItemResource that handles type discrimination.
/// </summary>
internal sealed class ItemResourceConverter : JsonConverter<ItemResource>
{
    /// <inheritdoc/>
    public override ItemResource? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using var doc = JsonDocument.ParseValue(ref reader);
        var root = doc.RootElement;

        if (!root.TryGetProperty("type", out var typeElement))
        {
            throw new JsonException("ItemResource must have a 'type' property");
        }

        var type = typeElement.GetString();

        // Determine the concrete type based on the type discriminator and deserialize using the source generation context
        return type switch
        {
            ResponsesMessageItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ResponsesMessageItemResource),
            FileSearchToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.FileSearchToolCallItemResource),
            FunctionToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.FunctionToolCallItemResource),
            FunctionToolCallOutputItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.FunctionToolCallOutputItemResource),
            ComputerToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ComputerToolCallItemResource),
            ComputerToolCallOutputItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ComputerToolCallOutputItemResource),
            WebSearchToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.WebSearchToolCallItemResource),
            ReasoningItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ReasoningItemResource),
            ItemReferenceItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ItemReferenceItemResource),
            ImageGenerationToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ImageGenerationToolCallItemResource),
            CodeInterpreterToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.CodeInterpreterToolCallItemResource),
            LocalShellToolCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.LocalShellToolCallItemResource),
            LocalShellToolCallOutputItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.LocalShellToolCallOutputItemResource),
            MCPListToolsItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPListToolsItemResource),
            MCPApprovalRequestItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPApprovalRequestItemResource),
            MCPApprovalResponseItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPApprovalResponseItemResource),
            MCPCallItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.MCPCallItemResource),
            ExecutorActionItemResource.ItemType => doc.Deserialize(OpenAIHostingJsonContext.Default.ExecutorActionItemResource),
            _ => null
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
            case ExecutorActionItemResource executorAction:
                JsonSerializer.Serialize(writer, executorAction, OpenAIHostingJsonContext.Default.ExecutorActionItemResource);
                break;
            default:
                throw new JsonException($"Unknown item type: {value.GetType().Name}");
        }
    }
}
