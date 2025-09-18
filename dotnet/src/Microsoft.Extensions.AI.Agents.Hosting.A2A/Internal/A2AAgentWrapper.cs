// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.Hosting.A2A.Converters;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.Hosting.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgentWrapper
{
    private readonly AIAgent _innerAgent;
    private readonly IActorClient _actorClient;

    public A2AAgentWrapper(
        IActorClient actorClient,
        AIAgent innerAgent,
        ILoggerFactory? loggerFactory = null)
    {
        this._actorClient = actorClient;
        this._innerAgent = innerAgent ?? throw new ArgumentNullException(nameof(innerAgent));
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        var contextId = messageSendParams.Message.ContextId ?? Guid.NewGuid().ToString();
        var messageId = messageSendParams.Message.MessageId;

        var actorId = new ActorId(type: this.GetActorType(), key: contextId!);

        // Verify request does not exist already
        var existingResponseHandle = await this._actorClient.GetResponseAsync(actorId, messageId, cancellationToken).ConfigureAwait(false);
        var existingResponse = await existingResponseHandle.GetResponseAsync(cancellationToken).ConfigureAwait(false);
        if (existingResponse.Status is RequestStatus.Completed or RequestStatus.Failed)
        {
            return existingResponse.ToMessage();
        }

        // here we know we did not yet send the request, so lets do it
        var chatMessages = messageSendParams.ToChatMessages();
        var runRequest = new AgentRunRequest
        {
            Messages = chatMessages
        };
        var @params = JsonSerializer.SerializeToElement(runRequest, AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunRequest)));

        var requestHandle = await this._actorClient.SendRequestAsync(new ActorRequest(actorId, messageId, method: "Run" /* ?refer to const here? */, @params: @params), cancellationToken).ConfigureAwait(false);
        var response = await requestHandle.GetResponseAsync(cancellationToken).ConfigureAwait(false);

        return response.ToMessage();
    }

    private ActorType GetActorType()
    {
        // agent is registered in DI via name
        ArgumentException.ThrowIfNullOrEmpty(this._innerAgent.Name);
        return new ActorType(this._innerAgent.Name);
    }
}
