// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.Agents.Persistent;
using Microsoft.Agents.AzureAI.Internal;
using Microsoft.Extensions.AI;
using System.Collections.Generic;

namespace Microsoft.Agents.AzureAI;

/// <summary>
/// Exposes patterns for creating and managing agent threads.
/// </summary>
/// <remarks>
/// This class supports translation of <see cref="ChatMessage"/> from native models.
/// </remarks>
public static class AzureAIThreadMessageFactory
{
    /// <summary>
    /// Translates <see cref="ChatMessage"/> to <see cref="ThreadMessageOptions"/> for thread creation.
    /// </summary>
    public static IEnumerable<ThreadMessageOptions> Translate(IEnumerable<ChatMessage> messages)
    {
        return AgentMessageFactory.GetThreadMessages(messages);
    }
}
