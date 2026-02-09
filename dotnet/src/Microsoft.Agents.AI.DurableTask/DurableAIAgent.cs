// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Entities;
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
    /// Creates a new agent session for this agent using a random session ID.
    /// </summary>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A value task that represents the asynchronous operation. The task result contains a new agent session.</returns>
    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
    {
        AgentSessionId sessionId = this._context.NewAgentSessionId(this._agentName);
        return ValueTask.FromResult<AgentSession>(new DurableAgentSession(sessionId));
    }

    /// <summary>
    /// Serializes an agent session to JSON.
    /// </summary>
    /// <param name="session">The session to serialize.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    /// <returns>A <see cref="JsonElement"/> containing the serialized session state.</returns>
    protected override JsonElement SerializeSessionCore(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (session is null)
        {
            throw new ArgumentNullException(nameof(session));
        }

        if (session is not DurableAgentSession durableSession)
        {
            throw new InvalidOperationException("The provided session is not compatible with the agent. Only sessions created by the agent can be serialized.");
        }

        return durableSession.Serialize(jsonSerializerOptions);
    }

    /// <summary>
    /// Deserializes an agent session from JSON.
    /// </summary>
    /// <param name="serializedState">The serialized session data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A value task that represents the asynchronous operation. The task result contains the deserialized agent session.</returns>
    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult<AgentSession>(DurableAgentSession.Deserialize(serializedState, jsonSerializerOptions));
    }

    /// <summary>
    /// Runs the agent with messages and returns the response.
    /// </summary>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="session">The agent session to use.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>The response from the agent.</returns>
    /// <exception cref="AgentNotRegisteredException">Thrown when the agent has not been registered.</exception>
    /// <exception cref="ArgumentException">Thrown when the provided session is not valid for a durable agent.</exception>
    /// <exception cref="NotSupportedException">Thrown when cancellation is requested (cancellation is not supported for durable agents).</exception>
    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (cancellationToken != default && cancellationToken.CanBeCanceled)
        {
            throw new NotSupportedException("Cancellation is not supported for durable agents.");
        }

        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        if (session is not DurableAgentSession durableSession)
        {
            throw new ArgumentException(
                "The provided session is not valid for a durable agent. " +
                "Create a new session using CreateSessionAsync or provide a session previously created by this agent.",
                paramName: nameof(session));
        }

        IList<string>? enableToolNames = null;
        bool enableToolCalls = true;
        ChatResponseFormat? responseFormat = null;
        if (options is DurableAgentRunOptions durableOptions)
        {
            enableToolCalls = durableOptions.EnableToolCalls;
            enableToolNames = durableOptions.EnableToolNames;
        }
        else if (options is ChatClientAgentRunOptions chatClientOptions && chatClientOptions.ChatOptions?.Tools != null)
        {
            // Honor the response format from the chat client options if specified
            responseFormat = chatClientOptions.ChatOptions?.ResponseFormat;
        }

        // Override the response format if specified in the agent run options
        if (options?.ResponseFormat is { } format)
        {
            responseFormat = format;
        }

        RunRequest request = new([.. messages], responseFormat, enableToolCalls, enableToolNames)
        {
            OrchestrationId = this._context.InstanceId
        };

        try
        {
            return await this._context.Entities.CallEntityAsync<AgentResponse>(
                durableSession.SessionId,
                nameof(AgentEntity.Run),
                request);
        }
        catch (EntityOperationFailedException e) when (e.FailureDetails.ErrorType == "EntityTaskNotFound")
        {
            throw new AgentNotRegisteredException(this._agentName, e);
        }
    }

    /// <summary>
    /// Runs the agent with messages and returns a simulated streaming response.
    /// </summary>
    /// <remarks>
    /// Streaming is not supported for durable agents, so this method just returns the full response
    /// as a single update.
    /// </remarks>
    /// <param name="messages">The messages to send to the agent.</param>
    /// <param name="session">The agent session to use.</param>
    /// <param name="options">Optional run options.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A streaming response enumerable.</returns>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Streaming is not supported for durable agents, so we just return the full response
        // as a single update.
        AgentResponse response = await this.RunAsync(messages, session, options, cancellationToken);
        foreach (AgentResponseUpdate update in response.ToAgentResponseUpdates())
        {
            yield return update;
        }
    }
}
