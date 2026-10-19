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
    internal static IList<AIContent>? ToAIContents(this TaskStatus status)
    {
        _ = Throw.IfNull(status);

        List<AIContent>? contents = null;

        // Status messages are optional, even for unsuccessful tasks.
        if (status.Message is null)
        {
            return contents;
        }

        // Skip status messages for routine progress and successful completion.
        if (status.State is TaskState.Submitted or TaskState.Working or TaskState.Completed)
        {
            return contents;
        }

        // Convert status messages for InputRequired, AuthRequired, Failed, Canceled, Rejected, and Unspecified.
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
