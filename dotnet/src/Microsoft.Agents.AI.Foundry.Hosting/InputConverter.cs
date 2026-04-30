// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Text.Json;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;
using SdkTextContent = Azure.AI.AgentServer.Responses.Models.TextContent;

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
    /// <param name="stateBag">Optional session state bag carrying the tool-approval id mapping.</param>
    /// <returns>A list of chat messages representing the request input.</returns>
    public static List<ChatMessage> ConvertInputToMessages(CreateResponse request, AgentSessionStateBag? stateBag = null)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in request.GetInputExpanded())
        {
            var message = ConvertInputItemToMessage(item, stateBag);
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
    /// <param name="stateBag">Optional session state bag carrying the tool-approval id mapping.</param>
    /// <returns>A list of chat messages.</returns>
    public static List<ChatMessage> ConvertItemsToMessages(IReadOnlyList<Item> items, AgentSessionStateBag? stateBag = null)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in items)
        {
            var message = ConvertInputItemToMessage(item, stateBag);
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
    /// <param name="stateBag">Optional session state bag carrying the tool-approval id mapping.</param>
    /// <returns>A list of chat messages.</returns>
    public static List<ChatMessage> ConvertOutputItemsToMessages(IReadOnlyList<OutputItem> items, AgentSessionStateBag? stateBag = null)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in items)
        {
            var message = ConvertOutputItemToMessage(item, stateBag);
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

    private static ChatMessage? ConvertInputItemToMessage(Item item, AgentSessionStateBag? stateBag)
    {
        return item switch
        {
            ItemMessage msg => ConvertItemMessage(msg),
            FunctionCallOutputItemParam funcOutput => ConvertFunctionCallOutput(funcOutput),
            ItemFunctionToolCall funcCall => ConvertItemFunctionToolCall(funcCall),
            ItemMcpApprovalRequest approvalRequest => ConvertMcpApprovalRequest(approvalRequest.Id, approvalRequest.Name, approvalRequest.Arguments),
            MCPApprovalResponse approvalResponse => ConvertMcpApprovalResponse(approvalResponse.ApprovalRequestId, approvalResponse.Approve, stateBag),
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
                case SdkTextContent textContent:
                    contents.Add(new MeaiTextContent(textContent.Text));
                    break;
                case SummaryTextContent summary:
                    contents.Add(new MeaiTextContent(summary.Text));
                    break;
                case MessageContentReasoningTextContent reasoning:
                    contents.Add(new TextReasoningContent(reasoning.Text));
                    break;
                case MessageContentInputImageContent imageContent:
                    AppendImageContent(contents, imageContent.ImageUrl, imageContent.FileId);
                    break;
                case MessageContentInputFileContent fileContent:
                    AppendFileContent(contents, fileContent.FileUrl, fileContent.FileData, fileContent.FileId, fileContent.Filename);
                    break;
                case ComputerScreenshotContent screenshot:
                    AppendImageContent(contents, screenshot.ImageUrl, screenshot.FileId);
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

    /// <summary>
    /// Converts an inbound <c>mcp_approval_request</c> wire item (from history replay
    /// or fresh-input) to a <see cref="ToolApprovalRequestContent"/> wrapping a
    /// <see cref="FunctionCallContent"/>. Mirrors python's
    /// <c>foundry_hosting/_responses.py</c> mapping.
    /// </summary>
    private static ChatMessage ConvertMcpApprovalRequest(string id, string name, string? arguments)
    {
        var functionCall = new FunctionCallContent(id, name, TryParseArguments(arguments));
        return new ChatMessage(
            ChatRole.Assistant,
            [new ToolApprovalRequestContent(id, functionCall)]);
    }

    /// <summary>
    /// Converts an inbound <c>mcp_approval_response</c> wire item to a
    /// <see cref="ToolApprovalResponseContent"/>. Looks up the original AF request id
    /// via <see cref="ToolApprovalIdMap"/>; falls back to the wire id when the mapping
    /// is unavailable. Carries a placeholder <see cref="FunctionCallContent"/> because
    /// the original tool-call details are not echoed by clients in the response item
    /// (matches python's behavior).
    /// </summary>
    private static ChatMessage ConvertMcpApprovalResponse(string approvalRequestId, bool approve, AgentSessionStateBag? stateBag)
    {
        var afRequestId = ToolApprovalIdMap.Resolve(stateBag, approvalRequestId);
        var placeholderFunctionCall = new FunctionCallContent(afRequestId, "mcp_approval");
        return new ChatMessage(
            ChatRole.User,
            [new ToolApprovalResponseContent(afRequestId, approve, placeholderFunctionCall)]);
    }

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing tool-call arguments from SDK input.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing tool-call arguments from SDK input.")]
    private static Dictionary<string, object?>? TryParseArguments(string? arguments)
    {
        if (string.IsNullOrWhiteSpace(arguments))
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<Dictionary<string, object?>>(arguments);
        }
        catch (JsonException)
        {
            return new Dictionary<string, object?> { ["_raw"] = arguments };
        }
    }

    private static ChatMessage? ConvertOutputItemToMessage(OutputItem item, AgentSessionStateBag? stateBag)
    {
        return item switch
        {
            OutputItemMessage msg => ConvertOutputItemMessageToChat(msg),
            OutputItemFunctionToolCall funcCall => ConvertOutputItemFunctionCall(funcCall),
            OutputItemFunctionToolCallOutput funcOutput => ConvertFunctionToolCallOutput(funcOutput),
            OutputItemMcpApprovalRequest approvalRequest => ConvertMcpApprovalRequest(approvalRequest.Id, approvalRequest.Name, approvalRequest.Arguments),
            OutputItemMcpApprovalResponseResource approvalResponse => ConvertMcpApprovalResponse(approvalResponse.ApprovalRequestId, approvalResponse.Approve, stateBag),
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
                case SdkTextContent textContent:
                    contents.Add(new MeaiTextContent(textContent.Text));
                    break;
                case SummaryTextContent summary:
                    contents.Add(new MeaiTextContent(summary.Text));
                    break;
                case MessageContentReasoningTextContent reasoning:
                    contents.Add(new TextReasoningContent(reasoning.Text));
                    break;
                case MessageContentRefusalContent refusal:
                    contents.Add(new MeaiTextContent($"[Refusal: {refusal.Refusal}]"));
                    break;
                case MessageContentInputImageContent imageContent:
                    AppendImageContent(contents, imageContent.ImageUrl, imageContent.FileId);
                    break;
                case MessageContentInputFileContent fileContent:
                    AppendFileContent(contents, fileContent.FileUrl, fileContent.FileData, fileContent.FileId, fileContent.Filename);
                    break;
                case ComputerScreenshotContent screenshot:
                    AppendImageContent(contents, screenshot.ImageUrl, screenshot.FileId);
                    break;
            }
        }

        if (contents.Count == 0)
        {
            contents.Add(new MeaiTextContent(string.Empty));
        }

        return new ChatMessage(role, contents);
    }

    private static void AppendImageContent(List<AIContent> contents, Uri? imageUrl, string? fileId)
    {
        if (imageUrl is not null)
        {
            var url = imageUrl.ToString();
            if (url.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
            {
                contents.Add(new DataContent(url, "image/*"));
            }
            else
            {
                contents.Add(new UriContent(imageUrl, "image/*"));
            }
        }
        else if (!string.IsNullOrEmpty(fileId))
        {
            contents.Add(new HostedFileContent(fileId));
        }
    }

    private static void AppendFileContent(List<AIContent> contents, Uri? fileUrl, string? fileData, string? fileId, string? filename)
    {
        if (fileUrl is not null)
        {
            var content = new UriContent(fileUrl, "application/octet-stream");
            if (!string.IsNullOrEmpty(filename))
            {
                content.AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = filename };
            }
            contents.Add(content);
            return;
        }

        if (!string.IsNullOrEmpty(fileData))
        {
            // Mirror python's _convert_file_data: if the data URI carries text/* content,
            // decode it inline as TextContent so {System.LastMessageText} (and other
            // text-only consumers) sees the file's body rather than an opaque blob.
            if (TryDecodeTextDataUri(fileData, filename, out var decodedText))
            {
                contents.Add(new MeaiTextContent(decodedText));
            }
            else
            {
                var dataContent = new DataContent(fileData, "application/octet-stream");
                if (!string.IsNullOrEmpty(filename))
                {
                    dataContent.AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = filename };
                }
                contents.Add(dataContent);
            }
            return;
        }

        if (!string.IsNullOrEmpty(fileId))
        {
            var hosted = new HostedFileContent(fileId);
            if (!string.IsNullOrEmpty(filename))
            {
                hosted.AdditionalProperties = new AdditionalPropertiesDictionary { ["filename"] = filename };
            }
            contents.Add(hosted);
            return;
        }

        if (!string.IsNullOrEmpty(filename))
        {
            contents.Add(new MeaiTextContent($"[File: {filename}]"));
        }
    }

    private static bool TryDecodeTextDataUri(string dataUri, string? filename, out string text)
    {
        text = string.Empty;
        if (!dataUri.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        const string Marker = ";base64,";
        int markerIndex = dataUri.IndexOf(Marker, StringComparison.OrdinalIgnoreCase);
        if (markerIndex < 0)
        {
            return false;
        }

        string mediaType = dataUri.Substring("data:".Length, markerIndex - "data:".Length);
        if (!mediaType.StartsWith("text/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string encoded = dataUri.Substring(markerIndex + Marker.Length);
        try
        {
            byte[] bytes = Convert.FromBase64String(encoded);
            string decoded = Encoding.UTF8.GetString(bytes);
            text = string.IsNullOrEmpty(filename) ? decoded : $"[File: {filename}]\n{decoded}";
            return true;
        }
        catch (FormatException)
        {
            return false;
        }
        catch (DecoderFallbackException)
        {
            return false;
        }
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
