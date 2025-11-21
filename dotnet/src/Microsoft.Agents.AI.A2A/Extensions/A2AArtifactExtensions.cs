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
        return new ChatMessage(ChatRole.Assistant, artifact.ToAIContents())
        {
            AdditionalProperties = artifact.Metadata.ToAdditionalProperties(),
            RawRepresentation = artifact,
        };
    }

    internal static List<AIContent> ToAIContents(this Artifact artifact)
    {
        return artifact.Parts.ConvertAll(part => part.ToAIContent());
    }
}
