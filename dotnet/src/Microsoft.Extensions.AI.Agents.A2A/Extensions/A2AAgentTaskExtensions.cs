// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Extension methods for the <see cref="AgentTask"/> class.
/// </summary>
internal static class A2AAgentTaskExtensions
{
    public static IList<ChatMessage> ToChatMessages(this AgentTask agentTask)
    {
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
