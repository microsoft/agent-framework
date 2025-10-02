// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace A2A;

/// <summary>
/// Extension methods for the <see cref="AgentTask"/> class.
/// </summary>
internal static class A2AAgentTaskExtensions
{
    internal static IList<ChatMessage> ToChatMessages(this AgentTask agentTask)
    {
        _ = Throw.IfNull(agentTask);

        List<ChatMessage> messages = [];

        if (agentTask.Artifacts is not null)
        {
            foreach (var artifact in agentTask.Artifacts)
            {
                messages.Add(artifact.ToChatMessage());
            }
        }

        return messages;
    }
}
