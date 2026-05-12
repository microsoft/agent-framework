// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="TaskStatus"/> class.
/// </summary>
internal static class AgentTaskStatusExtensions
{
    internal static IList<AIContent>? GetUserInputRequests(this TaskStatus status)
    {
        _ = Throw.IfNull(status);

        List<AIContent>? contents = null;

        if (status.Message is null || status.State is not TaskState.InputRequired)
        {
            return contents;
        }

        foreach (var part in status.Message.Parts)
        {
            var aiContent = part.ToAIContent();
            aiContent.RawRepresentation = part;
            aiContent.AdditionalProperties = part.Metadata.ToAdditionalProperties();
            (contents ??= []).Add(aiContent);
        }

        return contents;
    }
}
