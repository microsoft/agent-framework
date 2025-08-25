// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

internal static class AIAgentsAbstractionsExtensions
{
    public static ChatMessage ToChatMessage(this AgentRunResponseUpdate update)
    {
        return new ChatMessage
        {
            AuthorName = update.AuthorName,
            Contents = update.Contents,
            Role = update.Role ?? ChatRole.User,
            CreatedAt = update.CreatedAt,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation,
        };
    }

    public static ChatMessage UpdateWith(this ChatMessage baseMessage, AgentRunResponseUpdate update)
    {
        Debug.Assert(update.MessageId == null || baseMessage.MessageId == update.MessageId);

        List<AIContent> mergedContent = new(baseMessage.Contents);
        mergedContent.AddRange(update.Contents);

        return new ChatMessage
        {
            AuthorName = update.AuthorName ?? baseMessage.AuthorName,
            Contents = mergedContent,
            Role = update.Role ?? baseMessage.Role,
            CreatedAt = update.CreatedAt ?? baseMessage.CreatedAt,
            MessageId = baseMessage.MessageId,
            RawRepresentation = update.RawRepresentation ?? baseMessage.RawRepresentation,
        };
    }
}
