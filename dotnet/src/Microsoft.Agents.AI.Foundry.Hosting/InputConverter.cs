// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Converts Responses Server SDK input types to agent-framework <see cref="ChatMessage"/> types.
/// </summary>
internal static class InputConverter
{
    /// <summary>
    /// Converts the SDK <see cref="CreateResponse"/> request input items into a list of <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="request">The create response request from the SDK.</param>
    /// <returns>A list of chat messages representing the request input.</returns>
    public static List<ChatMessage> ConvertInputToMessages(CreateResponse request)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in request.GetInputExpanded())
        {
            var message = ConvertInputItemToMessage(item);
            if (message is not null)
            {
                messages.Add(message);
            }
        }

        return messages;
    }

    /// <summary>
    /// Converts resolved SDK <see cref="Item"/> input items into <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="items">The resolved input items from the SDK context.</param>
    /// <returns>A list of chat messages.</returns>
    public static List<ChatMessage> ConvertItemsToMessages(IReadOnlyList<Item> items)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in items)
        {
            var message = ConvertInputItemToMessage(item);
            if (message is not null)
            {
                messages.Add(message);
            }
        }

        return messages;
    }

    /// <summary>
    /// Converts resolved SDK <see cref="OutputItem"/> history/input items into <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="items">The resolved output items from the SDK context.</param>
    /// <returns>A list of chat messages.</returns>
    public static List<ChatMessage> ConvertOutputItemsToMessages(IReadOnlyList<OutputItem> items)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in items)
        {
            var message = ConvertOutputItemToMessage(item);
            if (message is not null)
            {
                messages.Add(message);
            }
        }

        return messages;
    }

    /// <summary>
    /// Creates <see cref="ChatOptions"/> from the SDK request properties.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>A configured <see cref="ChatOptions"/> instance.</returns>
    public static ChatOptions ConvertToChatOptions(CreateResponse request)
    {
        return new ChatOptions
        {
            Temperature = (float?)request.Temperature,
            TopP = (float?)request.TopP,
            MaxOutputTokens = (int?)request.MaxOutputTokens,
            // Note: We intentionally do NOT set ModelId from request.Model here.
            // The hosted agent already has its own model configured, and passing
            // the client-provided model would override it (causing failures when
            // clients send placeholder values like "hosted-agent").
        };
    }

    /// <summary>
    /// Extracts any Foundry Toolbox markers (<c>foundry-toolbox://</c>) from the request's
    /// MCP tool entries so the handler can resolve them server-side.
    /// </summary>
    /// <param name="request">The create response request.</param>
    /// <returns>A list of (name, optional version) pairs, one per detected marker. Never <see langword="null"/>.</returns>
    public static List<(string Name, string? Version)> ReadMcpToolboxMarkers(CreateResponse request)
    {
        var markers = new List<(string Name, string? Version)>();

        if (request.Tools is null)
        {
            return markers;
        }

        foreach (var tool in request.Tools)
        {
            if (tool is not MCPTool mcp || mcp.ServerUrl is null)
            {
                continue;
            }

            if (HostedMcpToolboxAITool.TryParseToolboxAddress(mcp.ServerUrl.ToString(), out var name, out var version))
            {
                markers.Add((name!, version));
            }
        }

        return markers;
    }

    private static ChatMessage? ConvertInputItemToMessage(Item item)
    {
        return item switch
        {
            ItemMessage msg => ConvertItemMessage(msg),
            FunctionCallOutputItemParam funcOutput => ConvertFunctionCallOutput(funcOutput),
            ItemFunctionToolCall funcCall => ConvertItemFunctionToolCall(funcCall),
            ItemReferenceParam => null,
            _ => null
        };
    }

    private static ChatMessage ConvertItemMessage(ItemMessage msg)
    {
        var role = ConvertMessageRole(msg.Role);
        var contents = new List<AIContent>();

        foreach (var content in msg.GetContentExpanded())
        {
            switch (content)
            {
                case MessageContentInputTextContent textContent:
                    contents.Add(new MeaiTextContent(textContent.Text));
                    break;
                case MessageContentInputImageContent imageContent:
                    if (imageContent.ImageUrl is not null)
                    {
                        var url = imageContent.ImageUrl.ToString();
                        if (url.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
                        {
                            contents.Add(new DataContent(url, "image/*"));
                        }
                        else
                        {
                            contents.Add(new UriContent(imageContent.ImageUrl, "image/*"));
                        }
                    }
                    else if (!string.IsNullOrEmpty(imageContent.FileId))
                    {
                        contents.Add(new HostedFileContent(imageContent.FileId));
                    }

                    break;
                case MessageContentInputFileContent fileContent:
                    if (fileContent.FileUrl is not null)
                    {
                        contents.Add(new UriContent(fileContent.FileUrl, "application/octet-stream"));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.FileData))
                    {
                        contents.Add(new DataContent(fileContent.FileData, "application/octet-stream"));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.FileId))
                    {
                        contents.Add(new HostedFileContent(fileContent.FileId));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.Filename))
                    {
                        contents.Add(new MeaiTextContent($"[File: {fileContent.Filename}]"));
                    }

                    break;
            }
        }

        if (contents.Count == 0)
        {
            contents.Add(new MeaiTextContent(string.Empty));
        }

        return new ChatMessage(role, contents);
    }

    private static ChatMessage ConvertFunctionCallOutput(FunctionCallOutputItemParam funcOutput)
    {
        var output = funcOutput.Output?.ToString() ?? string.Empty;
        return new ChatMessage(
            ChatRole.Tool,
            [new FunctionResultContent(funcOutput.CallId, output)]);
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing function call arguments from SDK input.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing function call arguments from SDK input.")]
    private static ChatMessage ConvertItemFunctionToolCall(ItemFunctionToolCall funcCall)
    {
        IDictionary<string, object?>? arguments = null;
        if (funcCall.Arguments is not null)
        {
            try
            {
                arguments = JsonSerializer.Deserialize<Dictionary<string, object?>>(funcCall.Arguments);
            }
            catch (JsonException)
            {
                arguments = new Dictionary<string, object?> { ["_raw"] = funcCall.Arguments };
            }
        }

        return new ChatMessage(
            ChatRole.Assistant,
            [new FunctionCallContent(funcCall.CallId, funcCall.Name, arguments)]);
    }

    private static ChatMessage? ConvertOutputItemToMessage(OutputItem item)
    {
        return item switch
        {
            OutputItemMessage msg => ConvertOutputItemMessageToChat(msg),
            OutputItemFunctionToolCall funcCall => ConvertOutputItemFunctionCall(funcCall),
            OutputItemFunctionToolCallOutput funcOutput => ConvertFunctionToolCallOutput(funcOutput),
            OutputItemReasoningItem => null,
            _ => null
        };
    }

    private static ChatMessage ConvertOutputItemMessageToChat(OutputItemMessage msg)
    {
        var role = ConvertMessageRole(msg.Role);
        var contents = new List<AIContent>();

        foreach (var content in msg.Content)
        {
            switch (content)
            {
                case MessageContentInputTextContent textContent:
                    contents.Add(new MeaiTextContent(textContent.Text));
                    break;
                case MessageContentOutputTextContent textContent:
                    contents.Add(new MeaiTextContent(textContent.Text));
                    break;
                case MessageContentRefusalContent refusal:
                    contents.Add(new MeaiTextContent($"[Refusal: {refusal.Refusal}]"));
                    break;
                case MessageContentInputImageContent imageContent:
                    if (imageContent.ImageUrl is not null)
                    {
                        var url = imageContent.ImageUrl.ToString();
                        if (url.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
                        {
                            contents.Add(new DataContent(url, "image/*"));
                        }
                        else
                        {
                            contents.Add(new UriContent(imageContent.ImageUrl, "image/*"));
                        }
                    }
                    else if (!string.IsNullOrEmpty(imageContent.FileId))
                    {
                        contents.Add(new HostedFileContent(imageContent.FileId));
                    }

                    break;
                case MessageContentInputFileContent fileContent:
                    if (fileContent.FileUrl is not null)
                    {
                        contents.Add(new UriContent(fileContent.FileUrl, "application/octet-stream"));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.FileData))
                    {
                        contents.Add(new DataContent(fileContent.FileData, "application/octet-stream"));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.FileId))
                    {
                        contents.Add(new HostedFileContent(fileContent.FileId));
                    }
                    else if (!string.IsNullOrEmpty(fileContent.Filename))
                    {
                        contents.Add(new MeaiTextContent($"[File: {fileContent.Filename}]"));
                    }

                    break;
            }
        }

        if (contents.Count == 0)
        {
            contents.Add(new MeaiTextContent(string.Empty));
        }

        return new ChatMessage(role, contents);
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing function call arguments from SDK output history.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing function call arguments from SDK output history.")]
    private static ChatMessage ConvertOutputItemFunctionCall(OutputItemFunctionToolCall funcCall)
    {
        IDictionary<string, object?>? arguments = null;
        if (funcCall.Arguments is not null)
        {
            try
            {
                arguments = JsonSerializer.Deserialize<Dictionary<string, object?>>(funcCall.Arguments);
            }
            catch (JsonException)
            {
                arguments = new Dictionary<string, object?> { ["_raw"] = funcCall.Arguments };
            }
        }

        return new ChatMessage(
            ChatRole.Assistant,
            [new FunctionCallContent(funcCall.CallId, funcCall.Name, arguments)]);
    }

    private static ChatMessage ConvertFunctionToolCallOutput(OutputItemFunctionToolCallOutput funcOutput)
    {
        return new ChatMessage(
            ChatRole.Tool,
            [new FunctionResultContent(funcOutput.CallId, funcOutput.Output)]);
    }

    private static ChatRole ConvertMessageRole(MessageRole role)
    {
        return role switch
        {
            MessageRole.User => ChatRole.User,
            MessageRole.Assistant => ChatRole.Assistant,
            MessageRole.System => ChatRole.System,
            MessageRole.Developer => new ChatRole("developer"),
            _ => ChatRole.User
        };
    }
}
