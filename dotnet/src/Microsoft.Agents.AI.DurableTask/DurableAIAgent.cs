// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.DurableTask;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// A durable AIAgent implementation that uses entity methods to interact with agent entities.
/// </summary>
public sealed class DurableAIAgent : AIAgent
{
    private readonly TaskOrchestrationContext _context;
    private readonly string _agentName;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableAIAgent"/> class.
    /// </summary>
    /// <param name="context">The orchestration context.</param>
    /// <param name="agentName">The name of the agent.</param>
    internal DurableAIAgent(TaskOrchestrationContext context, string agentName)
    {
        this._context = context;
        this._agentName = agentName;
    }

    /// <summary>
    /// Creates a new agent thread for this agent using a random session ID.
    /// </summary>
    /// <returns>A new agent thread.</returns>
    public override AgentThread GetNewThread()
    {
        AgentSessionId sessionId = this._context.NewAgentSessionId(this._agentName);
        return new DurableAgentThread(sessionId);
    }

    /// <summary>
    /// Deserializes an agent thread from JSON.
    /// </summary>
    /// <param name="serializedThread">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    /// <returns>The deserialized agent thread.</returns>
    public override AgentThread DeserializeThread(
        JsonElement serializedThread,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return DurableAgentThread.Deserialize(serializedThread, jsonSerializerOptions);
    }

    /// <summary>
    /// Runs the agent with messages and returns the response.
    /// </summary>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="thread">The agent thread to use.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The response from the agent.</returns>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (cancellationToken != default && cancellationToken.CanBeCanceled)
        {
            throw new NotSupportedException("Cancellation is not supported for durable agents.");
        }

        thread ??= this.GetNewThread();
        if (thread is not DurableAgentThread durableThread)
        {
            throw new ArgumentException(
                "The provided thread is not valid for a durable agent. " +
                "Create a new thread using GetNewThread or provide a thread previously created by this agent.",
                paramName: nameof(thread));
        }

        IList<string>? enableToolNames = null;
        bool enableToolCalls = true;
        ChatResponseFormat? responseFormat = null;
        if (options is DurableAgentRunOptions durableOptions)
        {
            enableToolCalls = durableOptions.EnableToolCalls;
            enableToolNames = durableOptions.EnableToolNames;
            responseFormat = durableOptions.ResponseFormat;
        }
        else if (options is ChatClientAgentRunOptions chatClientOptions && chatClientOptions.ChatOptions?.Tools != null)
        {
            // Honor the response format from the chat client options if specified
            responseFormat = chatClientOptions.ChatOptions?.ResponseFormat;
        }

        RunRequest request = new([.. messages], responseFormat, enableToolCalls, enableToolNames);
        return await this._context.Entities.CallEntityAsync<AgentRunResponse>(durableThread.SessionId, nameof(AgentEntity.RunAgentAsync), request);
    }

    /// <summary>
    /// Runs the agent with messages and returns a simulated streaming response.
    /// </summary>
    /// <remarks>
    /// Streaming is not supported for durable agents, so this method just returns the full response
    /// as a single update.
    /// </remarks>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="thread">The agent thread to use.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A streaming response enumerable.</returns>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Streaming is not supported for durable agents, so we just return the full response
        // as a single update.
        AgentRunResponse response = await this.RunAsync(messages, thread, options, cancellationToken);
        foreach (AgentRunResponseUpdate update in response.ToAgentRunResponseUpdates())
        {
            yield return update;
        }
    }

    /// <summary>
    /// Runs the agent with a message and returns the deserialized output as an instance of <typeparamref name="T"/>.
    /// </summary>
    /// <param name="message">The message to send to the agent.</param>
    /// <param name="thread">The agent thread to use.</param>
    /// <param name="serializerOptions">Optional JSON serializer options.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <typeparam name="T">The type of the output.</typeparam>
    /// <exception cref="ArgumentException">
    /// Thrown when the provided <paramref name="options"/> already contains a response schema.
    /// Thrown when the provided <paramref name="options"/> is not a <see cref="DurableAgentRunOptions"/>.
    /// </exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the agent response is empty or cannot be deserialized.
    /// </exception>
    /// <returns>The output from the agent.</returns>
    public async Task<AgentRunResponse<T>> RunAsync<T>(
        string message,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return await this.RunAsync<T>(
            messages: [new ChatMessage(ChatRole.User, message) { CreatedAt = DateTimeOffset.UtcNow }],
            thread,
            serializerOptions,
            options,
            cancellationToken);
    }

    /// <summary>
    /// Runs the agent with messages and returns the deserialized output as an instance of <typeparamref name="T"/>.
    /// </summary>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="thread">The agent thread to use.</param>
    /// <param name="serializerOptions">Optional JSON serializer options.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <typeparam name="T">The type of the output.</typeparam>
    /// <exception cref="ArgumentException">
    /// Thrown when the provided <paramref name="options"/> already contains a response schema.
    /// Thrown when the provided <paramref name="options"/> is not a <see cref="DurableAgentRunOptions"/>.
    /// </exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the agent response is empty or cannot be deserialized.
    /// </exception>
    /// <returns>The output from the agent.</returns>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Fallback to reflection-based deserialization is intentional for library flexibility with user-defined types.")]
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050", Justification = "Fallback to reflection-based deserialization is intentional for library flexibility with user-defined types.")]
    public async Task<AgentRunResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        options ??= new DurableAgentRunOptions();
        if (options is not DurableAgentRunOptions durableOptions)
        {
            throw new ArgumentException(
                "Response schema is only supported with DurableAgentRunOptions when using durable agents. " +
                "Cannot specify a response schema when calling RunAsync<T>.",
                paramName: nameof(options));
        }

        if (durableOptions.ResponseFormat is not null)
        {
            throw new ArgumentException(
                "A response schema is already defined in the provided DurableAgentRunOptions. " +
                "Cannot specify a response schema when calling RunAsync<T>.",
                paramName: nameof(options));
        }

        // Create the JSON schema for the response type
        durableOptions.ResponseFormat = ChatResponseFormat.ForJsonSchema<T>();

        AgentRunResponse response = await this.RunAsync(messages, thread, durableOptions, cancellationToken);

        // Deserialize the response text to the requested type
        if (string.IsNullOrEmpty(response.Text))
        {
            throw new InvalidOperationException("Agent response is empty and cannot be deserialized.");
        }

        serializerOptions ??= DurableAgentJsonUtilities.DefaultOptions;

        // Prefer source-generated metadata when available to support AOT/trimming scenarios.
        // Fallback to reflection-based deserialization for types without source-generated metadata.
        // This is necessary since T is a user-provided type that may not have [JsonSerializable] coverage.
        JsonTypeInfo? typeInfo = serializerOptions.GetTypeInfo(typeof(T));
        T? result = (typeInfo is JsonTypeInfo typedInfo
            ? (T?)JsonSerializer.Deserialize(response.Text, typedInfo)
            : JsonSerializer.Deserialize<T>(response.Text, serializerOptions))
            ?? throw new InvalidOperationException($"Failed to deserialize agent response to type {typeof(T).Name}.");

        return new DurableAIAgentRunResponse<T>(response, result);
    }

    private sealed class DurableAIAgentRunResponse<T>(AgentRunResponse response, T result)
        : AgentRunResponse<T>(response.AsChatResponse())
    {
        public override T Result { get; } = result;
    }
}
