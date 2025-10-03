// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="AgentMessage"/> class.
/// </summary>
internal static class A2AMessageExtensions
{
    internal static ChatMessage ToChatMessage(this AgentMessage message)
    {
        List<AIContent>? aiContents = null;

        foreach (var part in message.Parts)
        {
            (aiContents ??= []).Add(part.ToAIContent());
        }

        return new ChatMessage(ChatRole.Assistant, aiContents)
        {
            AdditionalProperties = message.Metadata.ToAdditionalProperties(),
            RawRepresentation = message,
        };
    }
}
