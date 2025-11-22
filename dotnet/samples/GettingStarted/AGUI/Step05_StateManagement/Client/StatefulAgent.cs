// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace RecipeClient;

/// <summary>
/// A delegating agent that manages client-side state and automatically attaches it to requests.
/// </summary>
/// <typeparam name="TState">The state type.</typeparam>
internal sealed class StatefulAgent<TState> : DelegatingAIAgent
    where TState : class, new()
{
    private readonly JsonSerializerOptions _jsonSerializerOptions;

    /// <summary>
    /// Gets or sets the current state.
    /// </summary>
    public TState State { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="StatefulAgent{TState}"/> class.
    /// </summary>
    /// <param name="innerAgent">The underlying agent to delegate to.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options for state serialization.</param>
    /// <param name="initialState">The initial state. If null, a new instance will be created.</param>
    public StatefulAgent(AIAgent innerAgent, JsonSerializerOptions jsonSerializerOptions, TState? initialState = null)
        : base(innerAgent)
    {
        this._jsonSerializerOptions = jsonSerializerOptions;
        this.State = initialState ?? new TState();
    }

    /// <inheritdoc />
    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this.RunStreamingAsync(messages, thread, options, cancellationToken)
            .ToAgentRunResponseAsync(cancellationToken);
    }

    /// <inheritdoc />
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Add state to messages
        List<ChatMessage> messagesWithState = [.. messages];

        // Serialize the state using AgentState wrapper
        byte[] stateBytes = JsonSerializer.SerializeToUtf8Bytes(
            this.State,
            this._jsonSerializerOptions.GetTypeInfo(typeof(TState)));
        DataContent stateContent = new(stateBytes, "application/json");
        ChatMessage stateMessage = new(ChatRole.System, [stateContent]);
        messagesWithState.Add(stateMessage);

        // Stream the response and update state when received
        await foreach (AgentRunResponseUpdate update in this.InnerAgent.RunStreamingAsync(messagesWithState, thread, options, cancellationToken))
        {
            // Check if this update contains a state snapshot
            foreach (AIContent content in update.Contents)
            {
                if (content is DataContent dataContent && dataContent.MediaType == "application/json")
                {
                    // Deserialize the state
                    TState? newState = JsonSerializer.Deserialize(
                        dataContent.Data.Span,
                        this._jsonSerializerOptions.GetTypeInfo(typeof(TState))) as TState;
                    if (newState != null)
                    {
                        this.State = newState;
                    }
                }
            }

            yield return update;
        }
    }
}
