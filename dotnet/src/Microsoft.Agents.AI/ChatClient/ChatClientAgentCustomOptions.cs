// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides extension methods for <see cref="ChatClientAgent"/> to enable discoverability of <see cref="ChatClientAgentRunOptions"/>.
/// </summary>
public partial class ChatClientAgent
{
    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the session.
    /// </summary>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    public Task<AgentResponse> RunAsync(
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync(session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a text message from the user.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    public Task<AgentResponse> RunAsync(
        string message,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync(message, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a single chat message.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    public Task<AgentResponse> RunAsync(
        ChatMessage message,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync(message, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a collection of chat messages.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input messages and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse"/> with the agent's output.</returns>
    public Task<AgentResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync(messages, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent in streaming mode without providing new input messages, relying on existing context and instructions.
    /// </summary>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentResponseUpdate"/> instances representing the streaming response.</returns>
    public IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync(
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync(session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent in streaming mode with a text message from the user.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentResponseUpdate"/> instances representing the streaming response.</returns>
    public IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync(
        string message,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync(message, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent in streaming mode with a single chat message.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentResponseUpdate"/> instances representing the streaming response.</returns>
    public IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync(
        ChatMessage message,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync(message, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent in streaming mode with a collection of chat messages.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input messages and any response updates generated during invocation.
    /// </param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentResponseUpdate"/> instances representing the streaming response.</returns>
    public IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync(messages, session, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the session, and requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    public Task<AgentResponse<T>> RunAsync<T>(
        AgentSession? session,
        JsonSerializerOptions? serializerOptions,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>(session, serializerOptions, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a text message from the user, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    public Task<AgentResponse<T>> RunAsync<T>(
        string message,
        AgentSession? session,
        JsonSerializerOptions? serializerOptions,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>(message, session, serializerOptions, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a single chat message, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    public Task<AgentResponse<T>> RunAsync<T>(
        ChatMessage message,
        AgentSession? session,
        JsonSerializerOptions? serializerOptions,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>(message, session, serializerOptions, (AgentRunOptions?)options, cancellationToken);

    /// <summary>
    /// Runs the agent with a collection of chat messages, requesting a response of the specified type <typeparamref name="T"/>.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="session">
    /// The conversation session to use for this invocation. If <see langword="null"/>, a new session will be created.
    /// The session will be updated with the input messages and any response messages generated during invocation.
    /// </param>
    /// <param name="serializerOptions">The JSON serialization options to use.</param>
    /// <param name="options">Configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentResponse{T}"/> with the agent's output.</returns>
    public Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session,
        JsonSerializerOptions? serializerOptions,
        ChatClientAgentRunOptions? options,
        CancellationToken cancellationToken = default) =>
        this.RunAsync<T>(messages, session, serializerOptions, (AgentRunOptions?)options, cancellationToken);
}
