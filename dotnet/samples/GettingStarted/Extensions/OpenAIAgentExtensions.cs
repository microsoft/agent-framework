// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
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
internal static class OpenAIAgentExtensions
{
    /// <summary>
    /// Runs the AI agent with a single OpenAI chat message and returns the response as a native OpenAI <see cref="ChatCompletion"/>.
    /// </summary>
    /// <param name="agent">The AI agent to run.</param>
    /// <param name="message">The OpenAI chat message to send to the agent.</param>
    /// <param name="thread">The conversation thread to continue with this invocation. If not provided, creates a new thread. The thread will be mutated with the provided message and agent response.</param>
    /// <param name="options">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="Task{ChatCompletion}"/> representing the asynchronous operation that returns a native OpenAI <see cref="ChatCompletion"/> response.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="agent"/> or <paramref name="message"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the agent's response cannot be converted to a <see cref="ChatCompletion"/>, typically when the underlying representation is not an OpenAI response.</exception>
    /// <exception cref="NotSupportedException">Thrown when the <paramref name="message"/> type is not supported by the <see cref="ToChatMessage"/> conversion method.</exception>
    /// <remarks>
    /// This method converts the OpenAI chat message to the Microsoft Extensions AI format using <see cref="ToChatMessage"/>,
    /// runs the agent, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// Currently only <see cref="UserChatMessage"/> types are supported for conversion.
    /// </remarks>
    internal static async Task<ChatCompletion> RunAsync(this AIAgent agent, OpenAI.Chat.ChatMessage message, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var response = await agent.RunAsync([message.ToChatMessage()], thread, options, cancellationToken);

        var chatCompletion = response.AsChatCompletion();
        return chatCompletion;
    }

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
    /// <exception cref="NotSupportedException">Thrown when any message in <paramref name="messages"/> has a type that is not supported by the <see cref="ToChatMessage"/> conversion method.</exception>
    /// <remarks>
    /// This method converts each OpenAI chat message to the Microsoft Extensions AI format using <see cref="ToChatMessage"/>,
    /// runs the agent with the converted message collection, and then extracts the native OpenAI <see cref="ChatCompletion"/> from the response using <see cref="AgentRunResponseExtensions.AsChatCompletion"/>.
    /// Currently only <see cref="UserChatMessage"/> types are supported for conversion.
    /// </remarks>
    internal static async Task<ChatCompletion> RunAsync(this AIAgent agent, IEnumerable<OpenAI.Chat.ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var response = await agent.RunAsync(messages.Select(m => m.ToChatMessage()).ToList(), thread, options, cancellationToken);

        var chatCompletion = response.AsChatCompletion();
        return chatCompletion;
    }

    /// <summary>
    /// Converts an OpenAI chat message to a Microsoft Extensions AI <see cref="Microsoft.Extensions.AI.ChatMessage"/>.
    /// </summary>
    /// <param name="chatMessage">The OpenAI chat message to convert.</param>
    /// <returns>A <see cref="Microsoft.Extensions.AI.ChatMessage"/> equivalent of the input OpenAI message.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="chatMessage"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">Thrown when the <paramref name="chatMessage"/> type is not supported for conversion.</exception>
    /// <remarks>
    /// <para>
    /// This method provides a bridge between OpenAI SDK message types and Microsoft Extensions AI message types.
    /// It enables seamless integration when working with both frameworks in the same application.
    /// </para>
    /// <para>
    /// Currently, only <see cref="UserChatMessage"/> is supported for conversion. The method extracts the text content
    /// from the first content item in the user message and creates a corresponding Microsoft Extensions AI user message.
    /// </para>
    /// <para>
    /// Future versions may extend support to additional OpenAI message types such as <c>AssistantChatMessage</c> and <c>SystemChatMessage</c>.
    /// </para>
    /// </remarks>
    internal static Microsoft.Extensions.AI.ChatMessage ToChatMessage(this OpenAI.Chat.ChatMessage chatMessage)
    {
        switch (chatMessage)
        {
            case UserChatMessage userMessage:
                return new Microsoft.Extensions.AI.ChatMessage(ChatRole.User, userMessage.Content.First().Text);
            default:
                throw new ArgumentException("Only support for user messages is implemented.");
        }
    }
}
