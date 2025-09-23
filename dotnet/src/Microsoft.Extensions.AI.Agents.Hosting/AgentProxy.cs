// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// Represents a proxy for an AI agent that communicates with the agent runtime via an actor client.
/// </summary>
public sealed class AgentProxy : AIAgent
{
    private readonly IActorClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentProxy"/> class with the specified agent name and actor client.
    /// </summary>
    /// <param name="name">The name of the agent.</param>
    /// <param name="client">The actor client used to communicate with the agent.</param>
    public AgentProxy(string name, IActorClient client)
    {
        this._client = Throw.IfNull(client, nameof(client));
        this.Name = Throw.IfNullOrEmpty(name, nameof(name));
    }

    /// <inheritdoc/>
    public override string Name { get; }

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => new AgentProxyThread();

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => new AgentProxyThread(serializedThread, jsonSerializerOptions);

    /// <summary>
    /// Gets a thread by its <see cref="AgentProxyThread.ConversationId"/>.
    /// </summary>
    /// <param name="conversationId">The thread identifier.</param>
    /// <returns>The thread.</returns>
    public AgentThread GetNewThread(string conversationId) => new AgentProxyThread(conversationId);

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages, nameof(messages));
        string agentThreadId = GetAgentThreadId(thread);
        return await this.RunAsync(messages, agentThreadId, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages, nameof(messages));
        string agentThreadId = GetAgentThreadId(thread);
        await foreach (var item in this.RunStreamingAsync(messages, agentThreadId, cancellationToken).ConfigureAwait(false))
        {
            yield return item;
        }
    }

    private async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, string threadId, CancellationToken cancellationToken)
    {
        var handle = await this.RunCoreAsync(messages, threadId, cancellationToken).ConfigureAwait(false);
        var response = await handle.GetResponseAsync(cancellationToken).ConfigureAwait(false);
        return response.Status switch
        {
            RequestStatus.Completed => (AgentRunResponse)response.Data.Deserialize(
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse)))!,
            RequestStatus.Failed => throw new InvalidOperationException($"The agent run request failed: {response.Data}"),
            RequestStatus.Pending => throw new InvalidOperationException("The agent run request is still pending."),
            _ => throw new NotSupportedException($"The agent run request returned an unsupported status: {response.Status}.")
        };
    }

    private async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        string threadId,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var response = await this.RunCoreAsync(messages, threadId, cancellationToken).ConfigureAwait(false);
        var updateTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
        await foreach (var update in response.WatchUpdatesAsync(cancellationToken).ConfigureAwait(false))
        {
            if (update.Status is RequestStatus.Failed)
            {
                throw new InvalidOperationException($"The agent run request failed: {update.Data}");
            }

            if (update.Status is RequestStatus.Completed)
            {
                yield break;
            }

            yield return (AgentRunResponseUpdate)update.Data.Deserialize(updateTypeInfo)!;
        }
    }

    private static string GetAgentThreadId(AgentThread? thread)
    {
        if (thread is null)
        {
            return AgentProxyThread.CreateId();
        }

        if (thread is not AgentProxyThread agentProxyThread)
        {
            throw new ArgumentException("The thread must be an instance of AgentProxyThread.", nameof(thread));
        }

        return agentProxyThread.ConversationId!;
    }

    private async Task<ActorResponseHandle> RunCoreAsync(IEnumerable<ChatMessage> messages, string threadId, CancellationToken cancellationToken)
    {
        List<ChatMessage> newMessages = [.. messages];

        var runRequest = new AgentRunRequest
        {
            Messages = newMessages
        };

        string messageId = newMessages.LastOrDefault()?.MessageId ?? Guid.NewGuid().ToString();
        ActorRequest actorRequest = new(
            actorId: new ActorId(this.Name, threadId),
            messageId,
            method: AgentActorConstants.RunMethodName,
            @params: JsonSerializer.SerializeToElement(runRequest, AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunRequest))));
        return await this._client.SendRequestAsync(actorRequest, cancellationToken).ConfigureAwait(false);
    }
}
