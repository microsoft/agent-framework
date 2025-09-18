// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.OpenAI.ChatCompletion;
using Microsoft.Shared.Diagnostics;
using OpenAI.Chat;

namespace OpenAI;

/// <summary>
/// Provides extension methods for <see cref="AIAgent"/> to simplify interaction with OpenAI chat messages
/// and return native OpenAI <see cref="ChatCompletion"/> responses.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between the Microsoft Extensions AI framework and the OpenAI SDK,
/// allowing developers to work with native OpenAI types while leveraging the AI Agent framework.
/// The methods handle the conversion between OpenAI chat message types and Microsoft Extensions AI types,
/// and return OpenAI <see cref="ChatCompletion"/> objects directly from the agent's <see cref="AgentRunResponse"/>.
/// </remarks>
public static class AIAgentWithOpenAIExtensions
{
    /// <summary>
    /// Runs the AI agent with a collection of OpenAI chat messages and returns the response as a native OpenAI <see cref="ChatCompletion"/>.
    /// </summary>
    /// <param name="agent">The AI agent to run.</param>
    /// <param name="messages">The collection of OpenAI chat messages to send to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided messages and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task{ChatCompletion}"/> representing the asynchronous operation that returns a native OpenAI <see cref="ChatCompletion"/> response.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> or <paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the agent's response cannot be converted to a <see cref="ChatCompletion"/>, typically when the underlying representation is not an OpenAI response.</exception>
    /// <exception cref="NotSupportedException">Thrown when any message in <paramref name="messages"/> has a type that is not supported by the message conversion method.</exception>
    /// <remarks>
    /// This method converts the OpenAI chat messages to the Microsoft Extensions AI format using the appropriate conversion method,
    /// runs the agent with the converted message collection, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// </remarks>
    public static async Task<ChatCompletion> RunAsync(this AIAgent agent, IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        var response = await agent.RunAsync([.. messages.AsChatMessages()], thread, options, cancellationToken).ConfigureAwait(false);

        return response.AsChatCompletion();
    }

    /// <summary>
    /// Runs the AI agent with a single OpenAI chat message and returns the response as collection of native OpenAI <see cref="StreamingChatCompletionUpdate"/>.
    /// </summary>
    /// <param name="agent">The AI agent to run.</param>
    /// <param name="messages">The collection of OpenAI chat messages to send to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided message and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task{ChatCompletion}"/> representing the asynchronous operation that returns a native OpenAI <see cref="ChatCompletion"/> response.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> or <paramref name="messages"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the agent's response cannot be converted to a <see cref="ChatCompletion"/>, typically when the underlying representation is not an OpenAI response.</exception>
    /// <exception cref="NotSupportedException">Thrown when the <paramref name="messages"/> type is not supported by the message conversion method.</exception>
    /// <remarks>
    /// This method converts the OpenAI chat messages to the Microsoft Extensions AI format using the appropriate conversion method,
    /// runs the agent, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// </remarks>
    public static AsyncCollectionResult<StreamingChatCompletionUpdate> RunStreamingAsync(this AIAgent agent, IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agent);
        Throw.IfNull(messages);

        IAsyncEnumerable<AgentRunResponseUpdate> response = agent.RunStreamingAsync([.. messages.AsChatMessages()], thread, options, cancellationToken);

        return new AsyncStreamingUpdateCollectionResult(response);
    }
}
