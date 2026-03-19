// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Converts stored <see cref="ItemResource"/> objects back to <see cref="ChatMessage"/> objects
/// for injecting conversation history into agent execution.
/// </summary>
internal static class ItemResourceConversions
{
    /// <summary>
    /// Converts a sequence of <see cref="ItemResource"/> items to a list of <see cref="ChatMessage"/> objects.
    /// Only converts message, function call, and function result items. Other item types are skipped.
    /// </summary>
    public static List<ChatMessage> ToChatMessages(IEnumerable<ItemResource> items)
    {
        var messages = new List<ChatMessage>();

        foreach (var item in items)
        {
            switch (item)
            {
                case ResponsesUserMessageItemResource userMsg:
                    messages.Add(new ChatMessage(ChatRole.User, ConvertContents(userMsg.Content)));
                    break;

                case ResponsesAssistantMessageItemResource assistantMsg:
                    messages.Add(new ChatMessage(ChatRole.Assistant, ConvertContents(assistantMsg.Content)));
                    break;

                case ResponsesSystemMessageItemResource systemMsg:
                    messages.Add(new ChatMessage(ChatRole.System, ConvertContents(systemMsg.Content)));
                    break;

                case ResponsesDeveloperMessageItemResource developerMsg:
                    messages.Add(new ChatMessage(new ChatRole("developer"), ConvertContents(developerMsg.Content)));
                    break;

                case FunctionToolCallItemResource funcCall:
                    var arguments = ParseArguments(funcCall.Arguments);
                    messages.Add(new ChatMessage(ChatRole.Assistant,
                    [
                        new FunctionCallContent(funcCall.CallId, funcCall.Name, arguments)
                    ]));
                    break;

                case FunctionToolCallOutputItemResource funcOutput:
                    messages.Add(new ChatMessage(ChatRole.Tool,
                    [
                        new FunctionResultContent(funcOutput.CallId, funcOutput.Output)
                    ]));
                    break;

                case MCPApprovalRequestItemResource mcpApproval:
                    var mcpArgs = ParseArguments(mcpApproval.Arguments);

                    // The mcp_approval_request spec item has a single Id field. MEAI reuses it as
                    // both the McpServerToolCallContent.CallId and the ToolApprovalRequestContent.RequestId
                    // because the spec doesn't provide a separate call ID.
                    var mcpToolCall = new McpServerToolCallContent(
                        mcpApproval.Id, mcpApproval.Name ?? string.Empty, mcpApproval.ServerLabel ?? string.Empty)
                    {
                        Arguments = mcpArgs
                    };
                    messages.Add(new ChatMessage(ChatRole.Assistant,
                    [
                        new ToolApprovalRequestContent(mcpApproval.Id, mcpToolCall)
                    ]));
                    break;

                    // Skip all other item types (reasoning, executor_action, web_search, etc.)
                    // They are not relevant for conversation context.
            }
        }

        return messages;
    }

    private static List<AIContent> ConvertContents(List<ItemContent> contents)
    {
        var result = new List<AIContent>();
        foreach (var content in contents)
        {
            var aiContent = ItemContentConverter.ToAIContent(content);
            if (aiContent is not null)
            {
                result.Add(aiContent);
            }
        }

        return result;
    }

    internal static Dictionary<string, object?>? ParseArguments(string? argumentsJson)
    {
        if (string.IsNullOrEmpty(argumentsJson))
        {
            return null;
        }

        try
        {
            using var doc = JsonDocument.Parse(argumentsJson);
            var result = new Dictionary<string, object?>();
            foreach (var property in doc.RootElement.EnumerateObject())
            {
                result[property.Name] = property.Value.ValueKind switch
                {
                    JsonValueKind.String => property.Value.GetString(),
                    JsonValueKind.Number => property.Value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.Null => null,
                    _ => property.Value.GetRawText()
                };
            }

            return result;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
