// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.A2A;
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
            (contents ??= []).Add(new A2AInputRequestContent(Guid.NewGuid().ToString("N"), part.ToAIContent())
            {
                RawRepresentation = part,
                AdditionalProperties = part.Metadata.ToAdditionalProperties(),
            });
        }

        return contents;
    }
}
