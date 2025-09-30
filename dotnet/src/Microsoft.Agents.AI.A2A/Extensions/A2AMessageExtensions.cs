// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="Message"/> class.
/// </summary>
internal static class A2AMessageExtensions
{
    internal static ChatMessage ToChatMessage(this Message message)
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
