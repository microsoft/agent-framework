// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AGUIChatMessageExtensions
{
    private static readonly ChatRole s_developerChatRole = new("developer");

    public static IEnumerable<ChatMessage> AsChatMessages(
        this IEnumerable<AGUIMessage> aguiMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        // Coalesce consecutive AGUIAssistantMessages that carry tool_calls into a single
        // ChatMessage. The AG-UI client (e.g. @ag-ui/client) creates a separate assistant
        // message per tool call when ToolCallStartEvent.parentMessageId is empty, but
        // OpenAI's chat-completion API requires every assistant message with tool_calls
        // to be IMMEDIATELY followed by tool responses for each of its tool_call_ids.
        // Sending two consecutive single-tool-call assistant messages before any tool
        // result triggers HTTP 400 "tool_call_ids did not have response messages".
        List<AIContent>? pendingContents = null;
        string? pendingId = null;

        foreach (var message in aguiMessages)
        {
            bool isAssistantWithToolCalls =
                message is AGUIAssistantMessage am && am.ToolCalls is { Length: > 0 };

            if (pendingContents is not null && !isAssistantWithToolCalls)
            {
                yield return CreateChatMessage(AGUIChatContentRole.Assistant, pendingContents, pendingId);
                pendingContents = null;
                pendingId = null;
            }

            var role = MapChatRole(message.Role);

            switch (message)
            {
                case AGUIToolMessage toolMessage:
                {
                    object? result;
                    string serializedContent = toolMessage.Content;
                    if (string.IsNullOrEmpty(serializedContent))
                    {
                        result = serializedContent;
                    }
                    else
                    {
                        // Try to deserialize as JSON, but fall back to string if it fails
                        try
                        {
                            result = JsonSerializer.Deserialize(serializedContent, AGUIJsonSerializerContext.Default.JsonElement);
                        }
                        catch (JsonException)
                        {
                            result = serializedContent;
                        }
                    }

                    yield return new ChatMessage(
                        role,
                        [
                            new FunctionResultContent(
                                    toolMessage.ToolCallId,
                                    result)
                        ]);
                    break;
                }

                case AGUIReasoningMessage reasoningMessage:
                {
                    var contents = new List<AIContent>();

                    if (!string.IsNullOrEmpty(reasoningMessage.Content))
                    {
                        contents.Add(new TextReasoningContent(reasoningMessage.Content)
                        {
                            ProtectedData = reasoningMessage.EncryptedValue
                        });
                    }
                    else if (!string.IsNullOrEmpty(reasoningMessage.EncryptedValue))
                    {
                        contents.Add(new TextReasoningContent(string.Empty)
                        {
                            ProtectedData = reasoningMessage.EncryptedValue
                        });
                    }

                    yield return new ChatMessage(role, contents)
                    {
                        MessageId = message.Id
                    };
                    break;
                }

                case AGUIAssistantMessage assistantMessage when assistantMessage.ToolCalls is { Length: > 0 }:
                {
                    pendingContents ??= [];
                    pendingId ??= message.Id;

                    AddChatMessageContents(
                        assistantMessage.Content,
                        pendingContents,
                        includeEmptyText: false);

                    foreach (var toolCall in assistantMessage.ToolCalls)
                    {
                        Dictionary<string, object?>? arguments = null;
                        if (!string.IsNullOrEmpty(toolCall.Function.Arguments))
                        {
                            arguments = (Dictionary<string, object?>?)JsonSerializer.Deserialize(
                                toolCall.Function.Arguments,
                                jsonSerializerOptions.GetTypeInfo(typeof(Dictionary<string, object?>)));
                        }

                        pendingContents.Add(new FunctionCallContent(
                            toolCall.Id,
                            toolCall.Function.Name,
                            arguments));
                    }

                    break;
                }

                default:
                {
                    List<AIContent> chatContents = GetChatMessageContents(message.Content, includeEmptyText: true).ToList();
                    if (chatContents.Count == 1 && chatContents[0] is TextContent textContent)
                    {
                        yield return new ChatMessage(role, textContent.Text)
                        {
                            MessageId = message.Id
                        };
                    }
                    else
                    {
                        yield return new ChatMessage(role, chatContents)
                        {
                            MessageId = message.Id
                        };
                    }

                    break;
                }
            }
        }

        // Flush remaining pending assistant-tool-call entry at end of stream.
        if (pendingContents is not null)
        {
            yield return CreateChatMessage(AGUIChatContentRole.Assistant, pendingContents, pendingId);
        }
    }

    public static IEnumerable<AGUIMessage> AsAGUIMessages(
        this IEnumerable<ChatMessage> chatMessages,
        JsonSerializerOptions jsonSerializerOptions)
    {
        foreach (var message in chatMessages)
        {
            message.MessageId ??= Guid.NewGuid().ToString("N");
            if (message.Role == ChatRole.Tool)
            {
                foreach (var toolMessage in MapToolMessages(jsonSerializerOptions, message))
                {
                    yield return toolMessage;
                }
            }
            else if (message.Role == ChatRole.Assistant)
            {
                var reasoningMessage = MapReasoningMessage(message);
                if (reasoningMessage != null)
                {
                    yield return reasoningMessage;
                }

                var assistantMessage = MapAssistantMessage(jsonSerializerOptions, message);
                if (assistantMessage != null)
                {
                    yield return assistantMessage;
                }
            }
            else
            {
                var content = CreateAGUIMessageContent(message.Contents);
                yield return message.Role.Value switch
                {
                    AGUIRoles.Developer => new AGUIDeveloperMessage
                    {
                        Id = message.MessageId,
                        Content = content
                    },
                    AGUIRoles.System => new AGUISystemMessage
                    {
                        Id = message.MessageId,
                        Content = content
                    },
                    AGUIRoles.User => new AGUIUserMessage
                    {
                        Id = message.MessageId,
                        Content = content
                    },
                    _ => throw new InvalidOperationException($"Unknown role: {message.Role.Value}")
                };
            }
        }
    }

    private static AGUIReasoningMessage? MapReasoningMessage(ChatMessage message)
    {
        var reasoning = message.Contents.OfType<TextReasoningContent>().FirstOrDefault();
        if (reasoning is null)
        {
            return null;
        }

        var text = string.Join(
            string.Empty,
            message.Contents.OfType<TextReasoningContent>()
                .Where(r => !string.IsNullOrEmpty(r.Text))
                .Select(r => r.Text));

        var protectedData = message.Contents.OfType<TextReasoningContent>()
            .Select(r => r.ProtectedData)
            .LastOrDefault(p => !string.IsNullOrEmpty(p));

        return new AGUIReasoningMessage
        {
            Id = message.MessageId,
            Content = text,
            EncryptedValue = protectedData,
        };
    }

    private static AGUIAssistantMessage? MapAssistantMessage(JsonSerializerOptions jsonSerializerOptions, ChatMessage message)
    {
        List<AGUIToolCall>? toolCalls = null;
        var messageContent = CreateAGUIMessageContent(message.Contents);

        foreach (var content in message.Contents)
        {
            if (content is FunctionCallContent functionCall)
            {
                var argumentsJson = functionCall.Arguments is null ?
                    "{}" :
                    JsonSerializer.Serialize(functionCall.Arguments, jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)));
                toolCalls ??= [];
                toolCalls.Add(new AGUIToolCall
                {
                    Id = functionCall.CallId,
                    Type = "function",
                    Function = new AGUIFunctionCall
                    {
                        Name = functionCall.Name,
                        Arguments = argumentsJson
                    }
                });
            }
        }

        if (toolCalls is null && messageContent.IsText && string.IsNullOrEmpty(messageContent.Text))
        {
            return null;
        }

        return new AGUIAssistantMessage
        {
            Id = message.MessageId,
            Content = messageContent,
            ToolCalls = toolCalls?.Count > 0 ? toolCalls.ToArray() : null
        };
    }

    private static AGUIMessageContent CreateAGUIMessageContent(IEnumerable<AIContent> chatContents)
    {
        List<AGUIMessageContentBlock> contentBlocks = [];

        foreach (var content in chatContents)
        {
            if (TryCreateMessageContentBlock(content, out var block))
            {
                contentBlocks.Add(block);
            }
        }

        if (contentBlocks.Count == 0)
        {
            return new AGUIMessageContent(string.Empty);
        }

        return contentBlocks.All(block => string.Equals(block.Type, "text", StringComparison.OrdinalIgnoreCase))
            ? new AGUIMessageContent(string.Concat(contentBlocks.Select(block => block.Text ?? string.Empty)))
            : new AGUIMessageContent(contentBlocks);
    }

    private static bool TryCreateMessageContentBlock(AIContent content, out AGUIMessageContentBlock block)
    {
        switch (content)
        {
            case TextContent textContent:
                block = new AGUIMessageContentBlock { Type = "text", Text = textContent.Text };
                return true;

            case UriContent uriContent:
                string? uri = uriContent.Uri?.ToString();
                block = BuildMediaContentBlock(
                    uriContent.MediaType ?? "application/octet-stream",
                    uri ?? string.Empty,
                    new AGUIMessageContentSource
                    {
                        Type = "url",
                        Value = uri ?? string.Empty,
                        MimeType = uriContent.MediaType
                    });
                return true;

            case DataContent dataContent when dataContent.Uri is { } dataUri && dataContent.Data.IsEmpty:
                {
                    var url = dataUri;
                    block = BuildMediaContentBlock(
                        ResolveMediaType(dataContent.MediaType),
                        url,
                        new AGUIMessageContentSource
                        {
                            Type = "url",
                            Value = url,
                            MimeType = ResolveMediaType(dataContent.MediaType)
                        });
                    return true;
                }

            case DataContent dataContent:
                {
                    string base64Data = Convert.ToBase64String(dataContent.Data.ToArray());
                    block = BuildMediaContentBlock(
                        ResolveMediaType(dataContent.MediaType),
                        base64Data,
                        new AGUIMessageContentSource
                        {
                            Type = "data",
                            Value = base64Data,
                            MimeType = ResolveMediaType(dataContent.MediaType)
                        },
                        dataContent.Name);
                    return true;
                }

            case HostedFileContent hostedFileContent:
                block = new AGUIMessageContentBlock
                {
                    Type = "document",
                    Id = hostedFileContent.FileId,
                    MimeType = ResolveMediaType(hostedFileContent.MediaType),
                    Filename = hostedFileContent.Name,
                    Source = null,
                };
                return true;

            default:
                block = new AGUIMessageContentBlock();
                return false;
        }
    }

    private static IEnumerable<AGUIMessage> MapToolMessages(JsonSerializerOptions jsonSerializerOptions, ChatMessage message)
    {
        foreach (var content in message.Contents)
        {
            if (content is FunctionResultContent functionResult)
            {
                yield return new AGUIToolMessage
                {
                    Id = functionResult.CallId,
                    ToolCallId = functionResult.CallId,
                    Content = functionResult.Result is null ?
                        string.Empty :
                        JsonSerializer.Serialize(functionResult.Result, jsonSerializerOptions.GetTypeInfo(functionResult.Result.GetType()))
                };
            }
        }
    }

    private static List<AIContent> GetChatMessageContents(AGUIMessageContent content, bool includeEmptyText)
    {
        var chatContents = new List<AIContent>();

        if (content.IsText)
        {
            if (includeEmptyText || !string.IsNullOrEmpty(content.Text))
            {
                chatContents.Add(new TextContent(content.Text));
            }

            return chatContents;
        }

        if (content.Blocks is { Length: > 0 } blocks)
        {
            foreach (var block in blocks)
            {
                if (TryConvertContentBlockToAIContent(block, out var aiContent))
                {
                    chatContents.Add(aiContent);
                }
            }

            return chatContents;
        }

        if (includeEmptyText)
        {
            chatContents.Add(new TextContent(string.Empty));
        }

        return chatContents;
    }

    private static void AddChatMessageContents(
        AGUIMessageContent content,
        List<AIContent> contents,
        bool includeEmptyText)
    {
        contents.AddRange(GetChatMessageContents(content, includeEmptyText));
    }

    private static bool TryConvertContentBlockToAIContent(
        AGUIMessageContentBlock block,
        out AIContent aiContent)
    {
        aiContent = null!;

        var type = (block.Type ?? string.Empty).Trim();
        var mediaType = Coalesce(block.MimeType, block.Source?.MimeType);

        return type switch
        {
            var t when string.Equals(t, "text", StringComparison.OrdinalIgnoreCase) => TryCreateTextContent(block, out aiContent),
            var t when string.Equals(t, "image", StringComparison.OrdinalIgnoreCase) ||
                       string.Equals(t, "audio", StringComparison.OrdinalIgnoreCase) ||
                       string.Equals(t, "video", StringComparison.OrdinalIgnoreCase) ||
                       string.Equals(t, "document", StringComparison.OrdinalIgnoreCase) ||
                       string.Equals(t, "file", StringComparison.OrdinalIgnoreCase) ||
                       string.Equals(t, "binary", StringComparison.OrdinalIgnoreCase) => TryCreateMediaContent(block, mediaType, out aiContent),
            _ => TryCreateTextContent(block, out aiContent)
        };
    }

    private static bool TryCreateTextContent(AGUIMessageContentBlock block, out AIContent aiContent)
    {
        aiContent = new TextContent(block.Text ?? string.Empty);
        return true;
    }

    private static bool TryCreateMediaContent(
        AGUIMessageContentBlock block,
        string mediaType,
        out AIContent aiContent)
    {
        aiContent = null!;

        var source = block.Source;
        var sourceType = (source?.Type ?? string.Empty).Trim();
        var sourceValue = Coalesce(source?.Value, block.Url);
        var sourceData = Coalesce(block.Data, string.Equals(sourceType, "data", StringComparison.OrdinalIgnoreCase) ? source?.Value : null);

        if (string.IsNullOrWhiteSpace(mediaType))
        {
            mediaType = "application/octet-stream";
        }

        if (string.Equals(sourceType, "url", StringComparison.OrdinalIgnoreCase) &&
            !string.IsNullOrWhiteSpace(sourceValue))
        {
            aiContent = new UriContent(sourceValue!, mediaType);
            return true;
        }

        if (string.Equals(sourceType, "data", StringComparison.OrdinalIgnoreCase) &&
            !string.IsNullOrWhiteSpace(sourceData))
        {
            try
            {
                aiContent = new DataContent(Convert.FromBase64String(sourceData), mediaType);
                return true;
            }
            catch (FormatException)
            {
            }
        }

        if (!string.IsNullOrEmpty(block.Id) &&
            string.IsNullOrEmpty(sourceType) &&
            string.IsNullOrEmpty(sourceValue) &&
            string.IsNullOrEmpty(sourceData))
        {
            HostedFileContent hostedFileContent = new(block.Id);
            if (!string.IsNullOrEmpty(block.MimeType))
            {
                hostedFileContent.MediaType = block.MimeType;
            }

            if (!string.IsNullOrEmpty(block.Filename))
            {
                hostedFileContent.Name = block.Filename;
            }

            aiContent = hostedFileContent;
            return true;
        }

        return TryCreateTextContent(block, out aiContent);
    }

    private static AGUIMessageContentBlock BuildMediaContentBlock(
        string mediaType,
        string value,
        AGUIMessageContentSource source,
        string? filename = null)
    {
        return new AGUIMessageContentBlock
        {
            Type = ResolveContentType(mediaType),
            Url = value,
            MimeType = mediaType,
            Filename = filename,
            Source = source
        };
    }

    private static string ResolveContentType(string mediaType)
    {
        if (string.IsNullOrWhiteSpace(mediaType))
        {
            return "document";
        }

        return mediaType.StartsWith("image/", StringComparison.OrdinalIgnoreCase)
            ? "image"
            : mediaType.StartsWith("audio/", StringComparison.OrdinalIgnoreCase)
            ? "audio"
            : mediaType.StartsWith("video/", StringComparison.OrdinalIgnoreCase)
            ? "video"
            : "document";
    }

    private static string ResolveMediaType(params string?[] mediaTypes)
    {
        foreach (var mediaType in mediaTypes)
        {
            if (!string.IsNullOrWhiteSpace(mediaType))
            {
                return mediaType;
            }
        }

        return "application/octet-stream";
    }

    private static string Coalesce(params string?[] values)
    {
        foreach (var value in values)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                return value;
            }
        }

        return string.Empty;
    }

    private static ChatMessage CreateChatMessage(AGUIChatContentRole role, List<AIContent> contents, string? messageId)
    {
        return role switch
        {
            AGUIChatContentRole.Assistant when contents.Count == 1 && contents[0] is TextContent textContent =>
                new ChatMessage(ChatRole.Assistant, textContent.Text)
                {
                    MessageId = messageId
                },
            _ => new ChatMessage(ChatRole.Assistant, contents)
            {
                MessageId = messageId
            }
        };
    }

    public static ChatRole MapChatRole(string role) =>
        string.Equals(role, AGUIRoles.System, StringComparison.OrdinalIgnoreCase) ? ChatRole.System :
        string.Equals(role, AGUIRoles.User, StringComparison.OrdinalIgnoreCase) ? ChatRole.User :
        string.Equals(role, AGUIRoles.Assistant, StringComparison.OrdinalIgnoreCase) ? ChatRole.Assistant :
        string.Equals(role, AGUIRoles.Developer, StringComparison.OrdinalIgnoreCase) ? s_developerChatRole :
        string.Equals(role, AGUIRoles.Tool, StringComparison.OrdinalIgnoreCase) ? ChatRole.Tool :
        string.Equals(role, AGUIRoles.Reasoning, StringComparison.OrdinalIgnoreCase) ? ChatRole.Assistant :
        throw new InvalidOperationException($"Unknown chat role: {role}");
}

internal enum AGUIChatContentRole
{
    Unknown,
    Assistant
}
