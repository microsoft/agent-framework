// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that delegates to an <see cref="IChatClient"/> implementation.
/// </summary>
public sealed partial class ChatClientAgent
{
    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread, and requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="useJsonSchemaResponseFormat">
    /// <see langword="true" /> to set a JSON schema on the <see cref="ChatResponseFormat"/>; otherwise, <see langword="false" />. The default is <see langword="true" />.
    /// Using a JSON schema improves reliability if the underlying model supports native structured output with a schema, but might cause an error if the model does not support it.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    /// <remarks>
    /// This overload is useful when the agent has sufficient context from previous messages in the thread
    /// or from its initial configuration to generate a meaningful response without additional input.
    /// </remarks>
    public Task<ChatClientAgentResponse<T>> RunAsync<T>(
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        bool? useJsonSchemaResponseFormat = null,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>([], thread, serializerOptions, options, useJsonSchemaResponseFormat, cancellationToken);

    /// <summary>
    /// Runs the agent with a text message from the user, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="useJsonSchemaResponseFormat">
    /// <see langword="true" /> to set a JSON schema on the <see cref="ChatResponseFormat"/>; otherwise, <see langword="false" />. The default is <see langword="true" />.
    /// Using a JSON schema improves reliability if the underlying model supports native structured output with a schema, but might cause an error if the model does not support it.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    /// <exception cref="ArgumentException"><paramref name="message"/> is <see langword="null"/>, empty, or contains only whitespace.</exception>
    /// <remarks>
    /// The provided text will be wrapped in a <see cref="ChatMessage"/> with the <see cref="ChatRole.User"/> role
    /// before being sent to the agent. This is a convenience method for simple text-based interactions.
    /// </remarks>
    public Task<ChatClientAgentResponse<T>> RunAsync<T>(
        string message,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        bool? useJsonSchemaResponseFormat = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunAsync<T>(new ChatMessage(ChatRole.User, message), thread, serializerOptions, options, useJsonSchemaResponseFormat, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a single chat message, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="useJsonSchemaResponseFormat">
    /// <see langword="true" /> to set a JSON schema on the <see cref="ChatResponseFormat"/>; otherwise, <see langword="false" />. The default is <see langword="true" />.
    /// Using a JSON schema improves reliability if the underlying model supports native structured output with a schema, but might cause an error if the model does not support it.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public Task<ChatClientAgentResponse<T>> RunAsync<T>(
        ChatMessage message,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        bool? useJsonSchemaResponseFormat = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunAsync<T>([message], thread, serializerOptions, options, useJsonSchemaResponseFormat, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a collection of chat messages, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input messages and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="useJsonSchemaResponseFormat">
    /// <see langword="true" /> to set a JSON schema on the <see cref="ChatResponseFormat"/>; otherwise, <see langword="false" />. The default is <see langword="true" />.
    /// Using a JSON schema improves reliability if the underlying model supports native structured output with a schema, but might cause an error if the model does not support it.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    /// <typeparam name="T">The type of structured output to request.</typeparam>
    /// <remarks>
    /// <para>
    /// This is the primary invocation method that implementations must override. It handles collections of messages,
    /// allowing for complex conversational scenarios including multi-turn interactions, function calls, and
    /// context-rich conversations.
    /// </para>
    /// <para>
    /// The messages are processed in the order provided and become part of the conversation history.
    /// The agent's response will also be added to <paramref name="thread"/> if one is provided.
    /// </para>
    /// </remarks>
    public Task<ChatClientAgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        bool? useJsonSchemaResponseFormat = null,
        CancellationToken cancellationToken = default)
    {
        async Task<ChatResponse<T>> GetResponseAsync(IChatClient chatClient, List<ChatMessage> threadMessages, ChatOptions? chatOptions, CancellationToken ct)
        {
            return await chatClient.GetResponseAsync<T>(
                threadMessages,
                serializerOptions ?? AgentJsonUtilities.DefaultOptions,
                chatOptions,
                useJsonSchemaResponseFormat,
                ct).ConfigureAwait(false);
        }

        static ChatClientAgentResponse<T> CreateResponse(ChatResponse<T> chatResponse)
        {
            return new ChatClientAgentResponse<T>(chatResponse)
            {
                ContinuationToken = WrapContinuationToken(chatResponse.ContinuationToken)
            };
        }

        return this.RunCoreAsync(GetResponseAsync, CreateResponse, messages, thread, options, cancellationToken);
    }
}
