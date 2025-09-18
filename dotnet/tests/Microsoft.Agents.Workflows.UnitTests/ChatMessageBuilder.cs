// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.UnitTests;

internal static class TextMessageStreamingExtensions
{
    public static IEnumerable<AIContent> ToContentStream(this string? message)
    {
        if (string.IsNullOrEmpty(message))
        {
            return [];
        }

        string[] splits = message.Split(' ');
        for (int i = 0; i < splits.Length - 1; i++)
        {
            splits[i] += " ";
        }

        return splits.Select(text => (AIContent)new TextContent(text) { RawRepresentation = text });
    }

    public static AgentRunResponseUpdate ToResponseUpdate(this AIContent content, string? messageId = null, DateTimeOffset? createdAt = null, string? responseId = null, string? agentId = null, string? authorName = null) =>
        new()
        {
            Role = ChatRole.Assistant,
            CreatedAt = createdAt ?? DateTimeOffset.Now,
            MessageId = messageId ?? Guid.NewGuid().ToString("N"),
            ResponseId = responseId,
            AgentId = agentId,
            AuthorName = authorName,
            Contents = [content],
        };

    public static IEnumerable<AgentRunResponseUpdate> ToAgentRunStream(this string message, DateTimeOffset? createdAt = null, string? messageId = null, string? responseId = null, string? agentId = null, string? authorName = null)
    {
        messageId ??= Guid.NewGuid().ToString("N");

        IEnumerable<AIContent> contents = message.ToContentStream();
        return contents.Select(content => content.ToResponseUpdate(messageId, createdAt, responseId, agentId, authorName));
    }

    public static ChatMessage ToChatMessage(this IEnumerable<AIContent> contents, string? messageId = null, DateTimeOffset? createdAt = null, string? responseId = null, string? agentId = null, string? authorName = null, string? rawRepresentation = null) =>
        new(ChatRole.Assistant, contents is List<AIContent> contentsList ? contentsList : contents.ToList())
        {
            AuthorName = authorName,
            CreatedAt = createdAt ?? DateTimeOffset.Now,
            MessageId = messageId ?? Guid.NewGuid().ToString("N"),
            RawRepresentation = rawRepresentation,
        };

    public static IEnumerable<AgentRunResponseUpdate> StreamMessage(this ChatMessage message, string? responseId = null, string? agentId = null)
    {
        responseId ??= Guid.NewGuid().ToString("N");
        string messageId = message.MessageId ?? Guid.NewGuid().ToString("N");

        return message.Contents.Select(content => content.ToResponseUpdate(messageId, message.CreatedAt, responseId: responseId, agentId: agentId, authorName: message.AuthorName));
    }

    public static IEnumerable<AgentRunResponseUpdate> StreamMessages(this List<ChatMessage> messages, string? agentId = null) =>
        messages.SelectMany(message => message.StreamMessage(agentId));

    public static List<ChatMessage> ToChatMessages(this IEnumerable<string> messages, string? authorName = null)
    {
        List<ChatMessage> result = messages.Select(ToMessage).ToList();

        ChatMessage ToMessage(string text)
        {
            return new(ChatRole.Assistant, text.ToContentStream().ToList())
            {
                AuthorName = authorName,
                MessageId = Guid.NewGuid().ToString("N"),
                RawRepresentation = text,
                CreatedAt = DateTimeOffset.Now,
            };
        }

        return result;
    }
}
