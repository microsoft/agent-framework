// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

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
}
