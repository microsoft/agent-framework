// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Orchestration;

/// <summary>Provides extensions for orchestrating <see cref="AIAgent"/>s.</summary>
public static class AIAgentExtensions
{
    private const string DefaultInstructions = "Respond with JSON that is populated by using the information in this conversation.";

    /// <summary>
    /// Runs the agent with the messages, then uses the chat client to process the agent's output and return a structured response.
    /// </summary>
    /// <typeparam name="T">The type of the result expected from the chat client response.</typeparam>
    /// <param name="agent">The AI agent to be run.</param>
    /// <param name="chatClient">The chat client used to process the messages.</param>
    /// <param name="message">The message to be processed.</param>
    /// <param name="thread">An optional thread context for the agent execution.</param>
    /// <param name="runOptions">Optional settings that influence the agent's execution.</param>
    /// <param name="serializerOptions">Optional serializer options to control how <typeparamref name="T"/> is deserialized.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation, with a result of type <typeparamref name="T"/> containing the
    /// structured response.</returns>
    public static ValueTask<T> RunAsync<T>(
        this AIAgent agent,
        IChatClient chatClient,
        string message,
        AgentThread? thread = null,
        AgentRunOptions? runOptions = null,
        JsonSerializerOptions? serializerOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(chatClient);
        Throw.IfNull(message);

        return RunAsync<T>(
            agent,
            chatClient,
            [new ChatMessage(ChatRole.User, message)],
            thread,
            runOptions,
            serializerOptions,
            cancellationToken);
    }

    /// <summary>
    /// Runs the agent with the messages, then uses the chat client to process the agent's output and return a structured response.
    /// </summary>
    /// <typeparam name="T">The type of the result expected from the chat client response.</typeparam>
    /// <param name="agent">The AI agent to be run.</param>
    /// <param name="chatClient">The chat client used to process the messages.</param>
    /// <param name="messages">A collection of chat messages to be processed.</param>
    /// <param name="thread">An optional thread context for the agent execution.</param>
    /// <param name="runOptions">Optional settings that influence the agent's execution.</param>
    /// <param name="serializerOptions">Optional serializer options to control how <typeparamref name="T"/> is deserialized.</param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation, with a result of type <typeparamref name="T"/> containing the
    /// structured response.</returns>
    public static async ValueTask<T> RunAsync<T>(
        this AIAgent agent,
        IChatClient chatClient,
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? runOptions = null,
        JsonSerializerOptions? serializerOptions = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(chatClient);
        Throw.IfNull(messages);

        // Invoke the agent.
        var response = await agent.RunAsync(messages, thread, runOptions, cancellationToken).ConfigureAwait(false);

        // Pass the output messages to the chat client to get a structured response.
        var result = await chatClient.GetResponseAsync<T>(
            response.Messages,
            serializerOptions: serializerOptions ?? AIJsonUtilities.DefaultOptions,
            new ChatOptions() { Instructions = DefaultInstructions },
            cancellationToken: cancellationToken).ConfigureAwait(false);

        // Parse and return the results.
        return result.Result;
    }
}
