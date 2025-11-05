// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

internal class DurableAIAgentProxy(string name, IDurableAgentClient agentClient) : AIAgent
{
    private readonly IDurableAgentClient _agentClient = agentClient;

    public override string? Name { get; } = name;

    public override AgentThread DeserializeThread(
        JsonElement serializedThread,
        JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return DurableAgentThread.Deserialize(serializedThread, jsonSerializerOptions);
    }

    public override AgentThread GetNewThread()
    {
        return new DurableAgentThread(AgentSessionId.WithRandomKey(this.Name!));
    }

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
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
            return new AgentRunResponse();
        }

        return await agentRunHandle.ReadAgentResponseAsync(cancellationToken);
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException("Streaming is not supported for durable agents.");
    }
}
