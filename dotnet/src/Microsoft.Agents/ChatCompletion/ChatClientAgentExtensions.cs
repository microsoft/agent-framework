// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Extensions for <see cref="ChatClientAgent"/> agent types.
/// </summary>
public static class ChatClientAgentExtensions
{
    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="agent">Target agent to run.</param>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="agentRunOptions">Optional parameters for agent invocation.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatResponse"/> containing the list of <see cref="ChatMessage"/> items.</returns>
    public static Task<ChatResponse> RunAsync(
        this ChatClientAgent agent,
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? agentRunOptions = null,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        return agent.RunAsync(messages, thread, new ChatClientAgentRunOptions(agentRunOptions, chatOptions), cancellationToken);
    }

    /// <summary>
    /// Run the agent with the provided message and arguments.
    /// </summary>
    /// <param name="agent">Target agent to run.</param>
    /// <param name="messages">The messages to pass to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent reponse.</param>
    /// <param name="agentRunOptions">Optional parameters for agent invocation.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public static IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        this ChatClientAgent agent,
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? agentRunOptions = null,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        return agent.RunStreamingAsync(messages, thread, new ChatClientAgentRunOptions(agentRunOptions, chatOptions), cancellationToken);
    }
}
