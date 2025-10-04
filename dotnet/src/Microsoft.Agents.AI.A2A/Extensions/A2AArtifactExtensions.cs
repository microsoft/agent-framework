// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="Artifact"/> class.
/// </summary>
internal static class A2AArtifactExtensions
{
    internal static ChatMessage ToChatMessage(this Artifact artifact)
    {
        List<AIContent>? aiContents = null;

        foreach (var part in artifact.Parts)
        {
            var content = part.ToAIContent();
            if (content is not null)
            {
                (aiContents ??= []).Add(content);
            }
        }

        return new ChatMessage(ChatRole.Assistant, aiContents)
        {
            AdditionalProperties = artifact.Metadata.ToAdditionalProperties(),
            RawRepresentation = artifact,
        };
    }
}
