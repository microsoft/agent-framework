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
                yield return new ChatMessage(ChatRole.Assistant, pendingContents) { MessageId = pendingId };
                pendingContents = null;
                pendingId = null;
            }

            var role = MapChatRole(message.Role);

            switch (message)
            {
                case AGUIToolMessage toolMessage:
                {
                    object? result;
                    if (string.IsNullOrEmpty(toolMessage.Content))
                    {
                        result = toolMessage.Content;
                    }
                    else
                    {
                        // Try to deserialize as JSON, but fall back to string if it fails
                        try
                        {
                            result = JsonSerializer.Deserialize(toolMessage.Content, AGUIJsonSerializerContext.Default.JsonElement);
                        }
                        catch (JsonException)
                        {
                            result = toolMessage.Content;
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
                        contents.Add(new TextReasoningContent("")
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
                    pendingContents ??= new List<AIContent>();
                    pendingId ??= message.Id;

                    if (!string.IsNullOrEmpty(assistantMessage.Content))
                    {
                        pendingContents.Add(new TextContent(assistantMessage.Content));
                    }

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
                    string content = message switch
                    {
                        AGUIDeveloperMessage dev => dev.Content,
                        AGUISystemMessage sys => sys.Content,
                        AGUIUserMessage => string.Empty,
                        AGUIAssistantMessage asst => asst.Content,
                        _ => string.Empty
                    };

                    if (message is AGUIUserMessage userMessage)
                    {
                        yield return new ChatMessage(role, MapUserContents(userMessage))
                        {
                            MessageId = message.Id,
                            AuthorName = userMessage.Name
                        };
                    }
                    else
                    {
                        yield return new ChatMessage(role, content)
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
            yield return new ChatMessage(ChatRole.Assistant, pendingContents) { MessageId = pendingId };
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
                yield return message.Role.Value switch
                {
                    AGUIRoles.Developer => new AGUIDeveloperMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                    AGUIRoles.System => new AGUISystemMessage { Id = message.MessageId, Content = message.Text ?? string.Empty },
                    AGUIRoles.User => MapUserMessage(message),
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
        string? textContent = null;

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
            else if (content is TextContent textContentItem)
            {
                textContent = textContentItem.Text;
            }
        }

        // Create message with tool calls and/or text content
        if (toolCalls?.Count > 0 || !string.IsNullOrEmpty(textContent))
        {
            return new AGUIAssistantMessage
            {
                Id = message.MessageId,
                Content = textContent ?? string.Empty,
                ToolCalls = toolCalls?.Count > 0 ? toolCalls.ToArray() : null
            };
        }

        return null;
    }

    private static IEnumerable<AGUIToolMessage> MapToolMessages(JsonSerializerOptions jsonSerializerOptions, ChatMessage message)
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

    public static ChatRole MapChatRole(string role) =>
        string.Equals(role, AGUIRoles.System, StringComparison.OrdinalIgnoreCase) ? ChatRole.System :
        string.Equals(role, AGUIRoles.User, StringComparison.OrdinalIgnoreCase) ? ChatRole.User :
        string.Equals(role, AGUIRoles.Assistant, StringComparison.OrdinalIgnoreCase) ? ChatRole.Assistant :
        string.Equals(role, AGUIRoles.Developer, StringComparison.OrdinalIgnoreCase) ? s_developerChatRole :
        string.Equals(role, AGUIRoles.Tool, StringComparison.OrdinalIgnoreCase) ? ChatRole.Tool :
        string.Equals(role, AGUIRoles.Reasoning, StringComparison.OrdinalIgnoreCase) ? ChatRole.Assistant :
        throw new InvalidOperationException($"Unknown chat role: {role}");

    private static List<AIContent> MapUserContents(AGUIUserMessage userMessage)
    {
        if (userMessage.InputContents is not { Length: > 0 })
        {
            return [new TextContent(userMessage.Content)];
        }

        List<AIContent> contents = [];
        foreach (AGUIInputContent inputContent in userMessage.InputContents)
        {
            switch (inputContent)
            {
                case AGUITextInputContent textInput:
                    contents.Add(new TextContent(textInput.Text));
                    break;
                case AGUIBinaryInputContent binaryInput:
                    contents.Add(MapBinaryInput(binaryInput));
                    break;
                default:
                    throw new InvalidOperationException($"Unsupported AG-UI input content type '{inputContent.GetType().Name}'.");
            }
        }

        return contents;
    }

    private static AIContent MapBinaryInput(AGUIBinaryInputContent binaryInput)
    {
        if (!string.IsNullOrEmpty(binaryInput.Data))
        {
            try
            {
                return new DataContent(Convert.FromBase64String(binaryInput.Data), binaryInput.MimeType ?? string.Empty)
                {
                    Name = binaryInput.Filename
                };
            }
            catch (FormatException ex)
            {
                throw new InvalidOperationException("AG-UI binary input content contains invalid base64 data.", ex);
            }
        }

        if (!string.IsNullOrEmpty(binaryInput.Url))
        {
            return new UriContent(binaryInput.Url, binaryInput.MimeType ?? string.Empty);
        }

        if (!string.IsNullOrEmpty(binaryInput.Id))
        {
            HostedFileContent hostedFileContent = new(binaryInput.Id)
            {
                Name = binaryInput.Filename
            };

            if (!string.IsNullOrEmpty(binaryInput.MimeType))
            {
                hostedFileContent.MediaType = binaryInput.MimeType;
            }

            return hostedFileContent;
        }

        throw new InvalidOperationException("AG-UI binary input content must include id, url, or data.");
    }

    private static AGUIUserMessage MapUserMessage(ChatMessage message)
    {
        List<AGUIInputContent> inputContents = [];
        foreach (AIContent content in message.Contents)
        {
            switch (content)
            {
                case TextContent textContent:
                    inputContents.Add(new AGUITextInputContent { Text = textContent.Text });
                    break;
                case DataContent dataContent:
                    inputContents.Add(new AGUIBinaryInputContent
                    {
                        MimeType = dataContent.MediaType,
                        Data = dataContent.Base64Data.ToString(),
                        Filename = dataContent.Name
                    });
                    break;
                case UriContent uriContent:
                    inputContents.Add(new AGUIBinaryInputContent
                    {
                        MimeType = uriContent.MediaType,
                        Url = uriContent.Uri.ToString()
                    });
                    break;
                case HostedFileContent hostedFileContent:
                    inputContents.Add(new AGUIBinaryInputContent
                    {
                        MimeType = hostedFileContent.MediaType,
                        Id = hostedFileContent.FileId,
                        Filename = hostedFileContent.Name
                    });
                    break;
                default:
                    throw new InvalidOperationException($"Unsupported user AI content type '{content.GetType().Name}'.");
            }
        }

        if (inputContents.Count == 1 &&
            inputContents[0] is AGUITextInputContent textInputContent)
        {
            return new AGUIUserMessage
            {
                Id = message.MessageId,
                Name = message.AuthorName,
                Content = textInputContent.Text
            };
        }

        if (inputContents.Count > 0)
        {
            return new AGUIUserMessage
            {
                Id = message.MessageId,
                Name = message.AuthorName,
                InputContents = [.. inputContents]
            };
        }

        return new AGUIUserMessage
        {
            Id = message.MessageId,
            Name = message.AuthorName,
            Content = message.Text ?? string.Empty
        };
    }
}
