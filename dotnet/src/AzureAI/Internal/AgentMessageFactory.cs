// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AzureAI.Internal;

/// <summary>
/// Factory for creating <see cref="MessageContent"/> based on <see cref="ChatMessage"/>.
/// </summary>
/// <remarks>
/// Improves testability.
/// </remarks>
internal static class AgentMessageFactory
{
    /// <summary>
    /// Translate metadata from a <see cref="ChatMessage"/> to be used for a <see cref="PersistentThreadMessage"/> or
    /// <see cref="ThreadMessageOptions"/>.
    /// </summary>
    /// <param name="message">The message content.</param>
    public static Dictionary<string, string> GetMetadata(ChatMessage message)
    {
        return message.AdditionalProperties?.ToDictionary(kvp => kvp.Key, kvp => kvp.Value?.ToString() ?? string.Empty) ?? [];
    }

    /// <summary>
    /// Translate attachments from a <see cref="ChatMessage"/> to be used for a <see cref="PersistentThreadMessage"/> or
    /// </summary>
    /// <param name="message">The message content.</param>
    public static IEnumerable<MessageAttachment> GetAttachments(ChatMessage message)
    {
        return new List<MessageAttachment>();
        /*
        return
            message.Contents
                .OfType<???>()
                .Select(
                    fileContent =>
                        new MessageAttachment(fileContent.FileId, [.. GetToolDefinition(fileContent.Tools)]));
        */
    }

    /// <summary>
    /// Translates a set of <see cref="ChatMessage"/> to a set of <see cref="ThreadMessageOptions"/>."/>
    /// </summary>
    /// <param name="messages">A list of <see cref="ChatMessage"/> objects/</param>
    public static IEnumerable<ThreadMessageOptions> GetThreadMessages(IEnumerable<ChatMessage>? messages)
    {
        if (messages is not null)
        {
            foreach (ChatMessage message in messages)
            {
                string? content = message.Text;
                if (string.IsNullOrWhiteSpace(content))
                {
                    continue;
                }

                ThreadMessageOptions threadMessage = new(
                    role: message.Role == ChatRole.User ? MessageRole.User : MessageRole.Agent,
                    content: message.Text)
                {
                    Attachments = [.. GetAttachments(message)],
                };

                if (message.AdditionalProperties != null)
                {
                    foreach (string key in message.AdditionalProperties.Keys)
                    {
                        threadMessage.Metadata = GetMetadata(message);
                    }
                }

                yield return threadMessage;
            }
        }
    }

    private static readonly Dictionary<string, ToolDefinition> s_toolMetadata = new()
    {
        { AzureAIAgent.Tools.CodeInterpreter, new CodeInterpreterToolDefinition() },
        { AzureAIAgent.Tools.FileSearch, new FileSearchToolDefinition() },
    };

    private static IEnumerable<ToolDefinition> GetToolDefinition(IEnumerable<string>? tools)
    {
        if (tools is null)
        {
            yield break;
        }

        foreach (string tool in tools)
        {
            if (s_toolMetadata.TryGetValue(tool, out ToolDefinition? toolDefinition))
            {
                yield return toolDefinition;
            }
        }
    }
}
