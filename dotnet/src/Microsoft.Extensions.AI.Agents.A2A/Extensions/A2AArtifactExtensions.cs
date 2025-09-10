// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

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
            (aiContents ??= []).Add(part.ToAIContent());
        }

        return new ChatMessage(ChatRole.Assistant, aiContents)
        {
            AdditionalProperties = artifact.Metadata.ToAdditionalProperties(),
            RawRepresentation = artifact,
        };
    }
}
