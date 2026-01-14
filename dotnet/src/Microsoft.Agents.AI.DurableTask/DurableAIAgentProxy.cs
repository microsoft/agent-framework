// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

internal class DurableAIAgentProxy(string name, IDurableAgentClient agentClient) : AIAgent
{
    private readonly IDurableAgentClient _agentClient = agentClient;

    public override string? Name { get; } = name;

    public override ValueTask<AgentThread> DeserializeThreadAsync(
        JsonElement serializedThread,
        JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult<AgentThread>(DurableAgentThread.Deserialize(serializedThread, jsonSerializerOptions));
    }

    public override ValueTask<AgentThread> GetNewThreadAsync(CancellationToken cancellationToken = default)
    {
        return ValueTask.FromResult<AgentThread>(new DurableAgentThread(AgentSessionId.WithRandomKey(this.Name!)));
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        thread ??= await this.GetNewThreadAsync(cancellationToken).ConfigureAwait(false);
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
        bool isFireAndForget = false;

        if (options is DurableAgentRunOptions durableOptions)
        {
            enableToolCalls = durableOptions.EnableToolCalls;
            enableToolNames = durableOptions.EnableToolNames;
            responseFormat = durableOptions.ResponseFormat;
            isFireAndForget = durableOptions.IsFireAndForget;
        }
        else if (options is ChatClientAgentRunOptions chatClientOptions)
        {
            // Honor the response format from the chat client options if specified
            responseFormat = chatClientOptions.ChatOptions?.ResponseFormat;
        }

        RunRequest request = new([.. messages], responseFormat, enableToolCalls, enableToolNames);
        AgentSessionId sessionId = durableThread.SessionId;

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
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException("Streaming is not supported for durable agents.");
    }
}
