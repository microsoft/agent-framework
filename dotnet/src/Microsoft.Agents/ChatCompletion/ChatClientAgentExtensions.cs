// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Represents an agent that can be invoked using a chat client.
/// </summary>
public static class ChatClientAgentExtensions
{
    /// <summary>
    /// Convenience method to run the agent with ChatOptions.
    /// </summary>
    /// <param name="agent">Target agent to run.</param>
    /// <param name="messages">Messages to send to the agent.</param>
    /// <param name="thread">Optional thread to use for the agent.</param>
    /// <param name="agentOptions">Optional agent run options.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <returns>A task representing the asynchronous operation, with the chat response.</returns>
    public static Task<ChatResponse> RunAsync(
        this ChatClientAgent agent,
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? agentOptions = null,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        if (chatOptions is not null)
        {
            agentOptions = new ChatClientAgentRunOptions { ChatOptions = chatOptions };
        }

        return agent.RunAsync(messages, thread, agentOptions, cancellationToken);
    }
}
