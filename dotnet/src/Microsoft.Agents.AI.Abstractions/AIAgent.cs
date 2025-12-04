// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides the base abstraction for all AI agents, defining the core interface for agent interactions and conversation management.
/// </summary>
/// <remarks>
/// <see cref="AIAgent"/> serves as the foundational class for implementing AI agents that can participate in conversations
/// and process user requests. An agent instance may participate in multiple concurrent conversations, and each conversation
/// may involve multiple agents working together.
/// </remarks>
[DebuggerDisplay("{DisplayName,nq}")]
public abstract class AIAgent
{
    /// <summary>Default ID of this agent instance.</summary>
    private readonly string _id = Guid.NewGuid().ToString("N");

    /// <summary>
    /// Gets the unique identifier for this agent instance.
    /// </summary>
    /// <value>
    /// A unique string identifier for the agent. For in-memory agents, this defaults to a randomly-generated ID,
    /// while service-backed agents typically use the identifier assigned by the backing service.
    /// </value>
    /// <remarks>
    /// Agent identifiers are used for tracking, telemetry, and distinguishing between different
    /// agent instances in multi-agent scenarios. They should remain stable for the lifetime
    /// of the agent instance.
    /// </remarks>
    public virtual string Id => this._id;

    /// <summary>
    /// Gets the human-readable name of the agent.
    /// </summary>
    /// <value>
    /// The agent's name, or <see langword="null"/> if no name has been assigned.
    /// </value>
    /// <remarks>
    /// The agent name is typically used for display purposes and to help users identify
    /// the agent's purpose or capabilities in user interfaces.
    /// </remarks>
    public virtual string? Name { get; }

    /// <summary>
    /// Gets a display-friendly name for the agent.
    /// </summary>
    /// <value>
    /// The agent's <see cref="Name"/> if available, otherwise the <see cref="Id"/>.
    /// </value>
    /// <remarks>
    /// This property provides a guaranteed non-null string suitable for display in user interfaces,
    /// logs, or other contexts where a readable identifier is needed.
    /// </remarks>
    public virtual string DisplayName => this.Name ?? this.Id ?? this._id; // final fallback to _id in case Id override returns null

    /// <summary>
    /// Gets a description of the agent's purpose, capabilities, or behavior.
    /// </summary>
    /// <value>
    /// A descriptive text explaining what the agent does, or <see langword="null"/> if no description is available.
    /// </value>
    /// <remarks>
    /// The description helps models and users understand the agent's intended purpose and capabilities,
    /// which is particularly useful in multi-agent systems.
    /// </remarks>
    public virtual string? Description { get; }

    /// <summary>Asks the <see cref="AIAgent"/> for an object of the specified type <paramref name="serviceType"/>.</summary>
    /// <param name="serviceType">The type of object being requested.</param>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="serviceType"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly-typed services that might be provided by the <see cref="AIAgent"/>,
    /// including itself or any services it might be wrapping. For example, to access the <see cref="AIAgentMetadata"/> for the instance,
    /// <see cref="GetService"/> may be used to request it.
    /// </remarks>
    public virtual object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        return serviceKey is null && serviceType.IsInstanceOfType(this)
            ? this
            : null;
    }

    /// <summary>Asks the <see cref="AIAgent"/> for an object of type <typeparamref name="TService"/>.</summary>
    /// <typeparam name="TService">The type of the object to be retrieved.</typeparam>
    /// <param name="serviceKey">An optional key that can be used to help identify the target service.</param>
    /// <returns>The found object, otherwise <see langword="null"/>.</returns>
    /// <remarks>
    /// The purpose of this method is to allow for the retrieval of strongly typed services that may be provided by the <see cref="AIAgent"/>,
    /// including itself or any services it might be wrapping.
    /// </remarks>
    public TService? GetService<TService>(object? serviceKey = null)
        => this.GetService(typeof(TService), serviceKey) is TService service ? service : default;

    /// <summary>
    /// Creates a new conversation thread that is compatible with this agent.
    /// </summary>
    /// <returns>A new <see cref="AgentThread"/> instance ready for use with this agent.</returns>
    /// <remarks>
    /// <para>
    /// This method creates a fresh conversation thread that can be used to maintain state
    /// and context for interactions with this agent. Each thread represents an independent
    /// conversation session.
    /// </para>
    /// <para>
    /// If the agent supports multiple thread types, this method returns the default or
    /// configured thread type. For service-backed agents, the actual thread creation
    /// may be deferred until first use to optimize performance.
    /// </para>
    /// </remarks>
    public abstract AgentThread GetNewThread();

    /// <summary>
    /// Deserializes an agent thread from its JSON serialized representation.
    /// </summary>
    /// <param name="serializedThread">A <see cref="JsonElement"/> containing the serialized thread state.</param>
    /// <param name="jsonSerializerOptions">Optional settings to customize the deserialization process.</param>
    /// <returns>A restored <see cref="AgentThread"/> instance with the state from <paramref name="serializedThread"/>.</returns>
    /// <exception cref="ArgumentException">The <paramref name="serializedThread"/> is not in the expected format.</exception>
    /// <exception cref="JsonException">The serialized data is invalid or cannot be deserialized.</exception>
    /// <remarks>
    /// This method enables restoration of conversation threads from previously saved state,
    /// allowing conversations to resume across application restarts or be migrated between
    /// different agent instances.
    /// </remarks>
    public abstract AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null);

    /// <summary>
    /// Run the agent with no message assuming that all required instructions are already provided to the agent or on the thread.
    /// </summary>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentRunResponse"/> with the agent's output.</returns>
    /// <remarks>
    /// This overload is useful when the agent has sufficient context from previous messages in the thread
    /// or from its initial configuration to generate a meaningful response without additional input.
    /// </remarks>
    public Task<AgentRunResponse> RunAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunAsync([], thread, options, cancellationToken);

    /// <summary>
    /// Runs the agent with a text message from the user.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentRunResponse"/> with the agent's output.</returns>
    /// <exception cref="ArgumentException"><paramref name="message"/> is <see langword="null"/>, empty, or contains only whitespace.</exception>
    /// <remarks>
    /// The provided text will be wrapped in a <see cref="ChatMessage"/> with the <see cref="ChatRole.User"/> role
    /// before being sent to the agent. This is a convenience method for simple text-based interactions.
    /// </remarks>
    public Task<AgentRunResponse> RunAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a single chat message.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentRunResponse"/> with the agent's output.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public Task<AgentRunResponse> RunAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent with a collection of chat messages, providing the core invocation logic that all other overloads delegate to.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input messages and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that represents the asynchronous operation. The task result contains an <see cref="AgentRunResponse"/> with the agent's output.</returns>
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
    public abstract Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Runs the agent in streaming mode without providing new input messages, relying on existing context and instructions.
    /// </summary>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentRunResponseUpdate"/> instances representing the streaming response.</returns>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default) =>
        this.RunStreamingAsync([], thread, options, cancellationToken);

    /// <summary>
    /// Runs the agent in streaming mode with a text message from the user.
    /// </summary>
    /// <param name="message">The user message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentRunResponseUpdate"/> instances representing the streaming response.</returns>
    /// <exception cref="ArgumentException"><paramref name="message"/> is <see langword="null"/>, empty, or contains only whitespace.</exception>
    /// <remarks>
    /// The provided text will be wrapped in a <see cref="ChatMessage"/> with the <see cref="ChatRole.User"/> role.
    /// Streaming invocation provides real-time updates as the agent generates its response.
    /// </remarks>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNullOrWhitespace(message);

        return this.RunStreamingAsync(new ChatMessage(ChatRole.User, message), thread, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent in streaming mode with a single chat message.
    /// </summary>
    /// <param name="message">The chat message to send to the agent.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input message and any response messages generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentRunResponseUpdate"/> instances representing the streaming response.</returns>
    /// <exception cref="ArgumentNullException"><paramref name="message"/> is <see langword="null"/>.</exception>
    public IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        ChatMessage message,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(message);

        return this.RunStreamingAsync([message], thread, options, cancellationToken);
    }

    /// <summary>
    /// Runs the agent in streaming mode with a collection of chat messages, providing the core streaming invocation logic.
    /// </summary>
    /// <param name="messages">The collection of messages to send to the agent for processing.</param>
    /// <param name="thread">
    /// The conversation thread to use for this invocation. If <see langword="null"/>, a new thread will be created.
    /// The thread will be updated with the input messages and any response updates generated during invocation.
    /// </param>
    /// <param name="options">Optional configuration parameters for controlling the agent's invocation behavior.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An asynchronous enumerable of <see cref="AgentRunResponseUpdate"/> instances representing the streaming response.</returns>
    /// <remarks>
    /// <para>
    /// This is the primary streaming invocation method that implementations must override. It provides real-time
    /// updates as the agent processes the input and generates its response, enabling more responsive user experiences.
    /// </para>
    /// <para>
    /// Each <see cref="AgentRunResponseUpdate"/> represents a portion of the complete response, allowing consumers
    /// to display partial results, implement progressive loading, or provide immediate feedback to users.
    /// </para>
    /// </remarks>
    public abstract IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);
}
