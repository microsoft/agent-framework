// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

internal class DurableAIAgentProxy(string name, IDurableAgentClient agentClient) : AIAgent
{
    private readonly IDurableAgentClient _agentClient = agentClient;

    public override string? Name { get; } = name;

    protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        if (session is null)
        {
            throw new ArgumentNullException(nameof(session));
        }

        if (session is not DurableAgentSession durableSession)
        {
            throw new InvalidOperationException($"The provided session type '{session.GetType().Name}' is not compatible with this agent. Only sessions of type '{nameof(DurableAgentSession)}' can be serialized by this agent.");
        }

        return new(durableSession.Serialize(jsonSerializerOptions));
    }

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult<AgentSession>(DurableAgentSession.Deserialize(serializedState, jsonSerializerOptions));
    }

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult<AgentSession>(new DurableAgentSession(AgentSessionId.WithRandomKey(this.Name!)));
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
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
        bool isFireAndForget = false;

        if (options is DurableAgentRunOptions durableOptions)
        {
            enableToolCalls = durableOptions.EnableToolCalls;
            enableToolNames = durableOptions.EnableToolNames;
            isFireAndForget = durableOptions.IsFireAndForget;
        }
        else if (options is ChatClientAgentRunOptions chatClientOptions)
        {
            // Honor the response format from the chat client options if specified
            responseFormat = chatClientOptions.ChatOptions?.ResponseFormat;
        }

        // Override the response format if specified in the agent run options
        if (options?.ResponseFormat is { } format)
        {
            responseFormat = format;
        }

        RunRequest request = new([.. messages], responseFormat, enableToolCalls, enableToolNames);
        AgentSessionId sessionId = durableSession.SessionId;

        AgentRunHandle agentRunHandle = await this._agentClient.RunAgentAsync(sessionId, request, cancellationToken);

        if (isFireAndForget)
        {
            // If the request is fire and forget, return an empty response.
            return new AgentResponse();
        }

        return await agentRunHandle.ReadAgentResponseAsync(cancellationToken);
    }

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException("Streaming is not supported for durable agents.");
    }
}
