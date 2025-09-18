// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

internal static class AIAgentsAbstractionsExtensions
{
    public static ChatMessage ToChatMessage(this AgentRunResponseUpdate update) =>
        new()
        {
            AuthorName = update.AuthorName,
            Contents = update.Contents,
            Role = update.Role ?? ChatRole.User,
            CreatedAt = update.CreatedAt,
            MessageId = update.MessageId,
            RawRepresentation = update.RawRepresentation ?? update,
        };

    public static ChatMessage UpdateWith(this ChatMessage baseMessage, AgentRunResponseUpdate update)
    {
        Debug.Assert(update.MessageId is null || baseMessage.MessageId == update.MessageId);

        return new()
        {
            AuthorName = update.AuthorName ?? baseMessage.AuthorName,
            Contents = [.. baseMessage.Contents, .. update.Contents],
            Role = update.Role ?? baseMessage.Role,
            CreatedAt = update.CreatedAt ?? baseMessage.CreatedAt,
            MessageId = baseMessage.MessageId,
            RawRepresentation = update.RawRepresentation ?? baseMessage.RawRepresentation ?? update,
        };
    }
}
