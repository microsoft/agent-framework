// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Represents a message in a conversation or response.
/// This is the unified type used for both conversation items and response output items.
/// </summary>
internal sealed record ConversationItem
{
    /// <summary>
    /// The unique identifier for the message.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    /// <summary>
    /// The object type, typically "message".
    /// </summary>
    [JsonPropertyName("type")]
    public string Type { get; init; } = "message";

    /// <summary>
    /// The conversation ID this message belongs to (optional, used in conversation context).
    /// </summary>
    [JsonPropertyName("conversation_id")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ConversationId { get; init; }

    /// <summary>
    /// The Unix timestamp (in seconds) for when the message was created.
    /// </summary>
    [JsonPropertyName("created_at")]
    public required long CreatedAt { get; init; }

    /// <summary>
    /// The role of the message author (user, assistant, system, etc.).
    /// </summary>
    [JsonPropertyName("role")]
    public required ChatRole Role { get; init; }

    /// <summary>
    /// The content of the message, stored as a JSON array of content items.
    /// Each item should have a "type" field (e.g., "text") and type-specific fields.
    /// Example: [{"type": "text", "text": "Hello"}]
    /// </summary>
    [JsonPropertyName("content")]
    public required JsonElement Content { get; init; }

    /// <summary>
    /// Set of key-value pairs that can be attached to a message.
    /// </summary>
    [JsonPropertyName("metadata")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, string>? Metadata { get; init; }

    /// <summary>
    /// Converts this Message to a ChatMessage for use with IChatClient.
    /// </summary>
    public ChatMessage ToChatMessage()
    {
        var contents = new List<AIContent>();

        if (this.Content.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in this.Content.EnumerateArray())
            {
                if (item.TryGetProperty("type", out var typeProperty))
                {
                    var contentType = typeProperty.GetString();

                    if (contentType == "text" || contentType == "input_text" || contentType == "output_text")
                    {
                        if (item.TryGetProperty("text", out var textProperty) && textProperty.ValueKind == JsonValueKind.String)
                        {
                            var text = textProperty.GetString();
                            if (!string.IsNullOrEmpty(text))
                            {
                                contents.Add(new TextContent(text));
                            }
                        }
                    }
                    else
                    {
                        // For other content types, deserialize using our context
                        // This works in both AOT and non-AOT scenarios
                        var aiContent = JsonSerializer.Deserialize(item.GetRawText(), ConversationsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent))) as AIContent;
                        if (aiContent is not null)
                        {
                            contents.Add(aiContent);
                        }
                    }
                }
            }
        }
        else if (this.Content.ValueKind == JsonValueKind.String)
        {
            // Handle simple string content
            var text = this.Content.GetString();
            if (!string.IsNullOrEmpty(text))
            {
                contents.Add(new TextContent(text));
            }
        }

        return new ChatMessage(this.Role, contents);
    }

    /// <summary>
    /// Creates a Message from a ChatMessage.
    /// </summary>
    public static ConversationItem FromChatMessage(ChatMessage chatMessage, string? conversationId = null, string? id = null, Dictionary<string, string>? metadata = null)
    {
        var contentArray = new List<object>();

        // Convert each AIContent item to a JSON-serializable object
        foreach (var content in chatMessage.Contents)
        {
            if (content is TextContent textContent)
            {
                var contentObj = new Dictionary<string, object>
                {
                    ["type"] = "text",
                    ["text"] = textContent.Text ?? string.Empty
                };

                // Include additional properties if present
                if (textContent.AdditionalProperties?.Count > 0)
                {
                    foreach (var kvp in textContent.AdditionalProperties)
                    {
                        if (kvp.Value is not null)
                        {
                            contentObj[kvp.Key] = kvp.Value;
                        }
                    }
                }

                contentArray.Add(contentObj);
            }
            else
            {
                // For non-text content, serialize using our context
                // This works in both AOT and non-AOT scenarios
                var element = JsonSerializer.SerializeToElement(content, ConversationsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent)));
                contentArray.Add(element);
            }
        }

        // If no content items were added, create a default empty text content
        if (contentArray.Count == 0 && !string.IsNullOrEmpty(chatMessage.Text))
        {
            contentArray.Add(new Dictionary<string, object>
            {
                ["type"] = "text",
                ["text"] = chatMessage.Text
            });
        }

        // Serialize using ConversationsJsonContext for AOT compatibility
        var contentJson = JsonSerializer.Serialize(contentArray, ConversationsJsonContext.Default.ListDictionaryStringObject);
        var contentElement = JsonDocument.Parse(contentJson).RootElement;

        return new ConversationItem
        {
            Id = id ?? $"msg_{Guid.NewGuid():N}",
            Type = "message",
            ConversationId = conversationId,
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Role = chatMessage.Role,
            Content = contentElement,
            Metadata = metadata
        };
    }

    /// <summary>
    /// Creates a Message with text content.
    /// </summary>
    public static ConversationItem CreateTextMessage(ChatRole role, string text, string? conversationId = null, string? id = null, Dictionary<string, string>? metadata = null)
    {
        var contentArray = new[]
        {
            new Dictionary<string, object>
            {
                ["type"] = "text",
                ["text"] = text
            }
        };

        // Serialize using ConversationsJsonContext for AOT compatibility
        var contentElement = JsonSerializer.SerializeToElement(contentArray, ConversationsJsonContext.Default.DictionaryStringObjectArray);

        return new ConversationItem
        {
            Id = id ?? $"msg_{Guid.NewGuid():N}",
            Type = "message",
            ConversationId = conversationId,
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Role = role,
            Content = contentElement,
            Metadata = metadata
        };
    }
}
