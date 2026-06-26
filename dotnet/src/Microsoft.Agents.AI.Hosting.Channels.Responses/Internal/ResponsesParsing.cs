// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.Responses;

/// <summary>
/// Parses the OpenAI Responses request body into Agent Framework constructs: the <c>input</c> field (string
/// or input-item array) into a <see cref="ChatMessage"/> list, the generation-control fields into
/// <see cref="ChatOptions"/>, and the caller identity into a <see cref="ChannelIdentity"/>. Mirrors the Python
/// <c>_parsing</c> module. Malformed shapes raise <see cref="FormatException"/> (HTTP 422).
/// </summary>
internal static class ResponsesParsing
{
    /// <summary>Translate <c>input</c> (string or list of items) into messages.</summary>
    public static IReadOnlyList<ChatMessage> MessagesFromInput(JsonElement? input)
    {
        if (input is null || input.Value.ValueKind == JsonValueKind.Null)
        {
            throw new FormatException("`input` must be a non-empty string or list");
        }

        var value = input.Value;

        if (value.ValueKind == JsonValueKind.String)
        {
            return [new ChatMessage(ChatRole.User, value.GetString() ?? string.Empty)];
        }

        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() == 0)
        {
            throw new FormatException("`input` must be a non-empty string or list");
        }

        var messages = new List<ChatMessage>();
        var pendingUserParts = new List<AIContent>();

        void Flush()
        {
            if (pendingUserParts.Count > 0)
            {
                messages.Add(new ChatMessage(ChatRole.User, new List<AIContent>(pendingUserParts)));
                pendingUserParts.Clear();
            }
        }

        foreach (var item in value.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object)
            {
                throw new FormatException("each `input` item must be an object");
            }

            if (item.TryGetProperty("type", out var typeEl) && typeEl.ValueKind == JsonValueKind.String && typeEl.GetString() == "message")
            {
                Flush();
                var role = item.TryGetProperty("role", out var roleEl) && roleEl.ValueKind == JsonValueKind.String
                    ? roleEl.GetString() ?? "user"
                    : "user";

                var parts = new List<AIContent>();
                if (item.TryGetProperty("content", out var content))
                {
                    if (content.ValueKind == JsonValueKind.String)
                    {
                        parts.Add(new TextContent(content.GetString() ?? string.Empty));
                    }
                    else if (content.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var contentItem in content.EnumerateArray())
                        {
                            if (contentItem.ValueKind != JsonValueKind.Object)
                            {
                                throw new FormatException("each message `content` item must be an object");
                            }

                            parts.Add(ContentFromInputItem(contentItem));
                        }
                    }
                    else if (content.ValueKind != JsonValueKind.Null)
                    {
                        throw new FormatException("message `content` must be a string or list");
                    }
                }

                messages.Add(new ChatMessage(MapRole(role), parts));
            }
            else
            {
                pendingUserParts.Add(ContentFromInputItem(item));
            }
        }

        Flush();

        if (messages.Count == 0)
        {
            throw new FormatException("`input` produced no messages");
        }

        return messages;
    }

    /// <summary>Build <see cref="ChatOptions"/> from the generation-control fields, or <see langword="null"/> when none are set.</summary>
    public static ChatOptions? BuildOptions(ResponsesRequestModel body)
    {
        ChatOptions? options = null;

        ChatOptions Ensure() => options ??= new ChatOptions();

        if (!string.IsNullOrEmpty(body.Instructions))
        {
            Ensure().Instructions = body.Instructions;
        }

        if (body.Temperature is { } temperature)
        {
            Ensure().Temperature = (float)temperature;
        }

        if (body.TopP is { } topP)
        {
            Ensure().TopP = (float)topP;
        }

        if (body.MaxOutputTokens is { } maxOutputTokens)
        {
            Ensure().MaxOutputTokens = maxOutputTokens;
        }

        if (body.ParallelToolCalls is { } parallelToolCalls)
        {
            Ensure().AllowMultipleToolCalls = parallelToolCalls;
        }

        return options;
    }

    /// <summary>Surface the caller as a <see cref="ChannelIdentity"/> via <c>safety_identifier</c> (falling back to <c>user</c>).</summary>
    public static ChannelIdentity? ParseIdentity(ResponsesRequestModel body, string channelName)
    {
        var native = !string.IsNullOrEmpty(body.SafetyIdentifier) ? body.SafetyIdentifier : body.User;
        return string.IsNullOrEmpty(native) ? null : new ChannelIdentity(channelName, native!);
    }

    private static AIContent ContentFromInputItem(JsonElement item)
    {
        var type = item.TryGetProperty("type", out var typeEl) && typeEl.ValueKind == JsonValueKind.String
            ? typeEl.GetString()
            : null;

        switch (type)
        {
            case "input_text":
            case "output_text":
            case "text":
                return new TextContent(item.TryGetProperty("text", out var textEl) && textEl.ValueKind == JsonValueKind.String
                    ? textEl.GetString() ?? string.Empty
                    : string.Empty);

            case "input_image":
                var imageUrl = ReadImageUrl(item);
                if (string.IsNullOrEmpty(imageUrl))
                {
                    throw new FormatException("input_image requires `image_url`");
                }

                return new UriContent(imageUrl!, "image/*");

            case "input_file":
                if (item.TryGetProperty("file_url", out var fileUrlEl) && fileUrlEl.ValueKind == JsonValueKind.String && !string.IsNullOrEmpty(fileUrlEl.GetString()))
                {
                    var mime = item.TryGetProperty("mime_type", out var mimeEl) && mimeEl.ValueKind == JsonValueKind.String
                        ? mimeEl.GetString()
                        : null;
                    return new UriContent(fileUrlEl.GetString()!, mime ?? "application/octet-stream");
                }

                if (item.TryGetProperty("file_id", out var fileIdEl) && fileIdEl.ValueKind == JsonValueKind.String && !string.IsNullOrEmpty(fileIdEl.GetString()))
                {
                    return new HostedFileContent(fileIdEl.GetString()!);
                }

                throw new FormatException("input_file requires `file_url` or `file_id`");

            default:
                throw new FormatException($"Unsupported Responses input content type: '{type}'");
        }
    }

    private static string? ReadImageUrl(JsonElement item)
    {
        if (!item.TryGetProperty("image_url", out var imageUrl))
        {
            return null;
        }

        if (imageUrl.ValueKind == JsonValueKind.String)
        {
            return imageUrl.GetString();
        }

        if (imageUrl.ValueKind == JsonValueKind.Object && imageUrl.TryGetProperty("url", out var urlEl) && urlEl.ValueKind == JsonValueKind.String)
        {
            return urlEl.GetString();
        }

        return null;
    }

    private static ChatRole MapRole(string? role) => role switch
    {
        "assistant" => ChatRole.Assistant,
        "system" or "developer" => ChatRole.System,
        "tool" => ChatRole.Tool,
        _ => ChatRole.User,
    };
}
