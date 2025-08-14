// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI.Agents.A2A.Converters;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgentWrapper
{
    private readonly ILogger _logger;
    private readonly TaskManager _taskManager;
    private readonly AIAgent _innerAgent;
    private readonly IActorClient _actorClient;

    public A2AAgentWrapper(
        IActorClient actorClient,
        AIAgent innerAgent,
        TaskManager taskManager,
        ILoggerFactory? loggerFactory = null)
    {
        this._logger = (loggerFactory ?? NullLoggerFactory.Instance).CreateLogger<A2AAgentWrapper>();

        this._actorClient = actorClient;
        this._taskManager = taskManager ?? throw new ArgumentNullException(nameof(taskManager));
        this._innerAgent = innerAgent ?? throw new ArgumentNullException(nameof(innerAgent));
    }

    public async Task<Message> ProcessMessageAsync(MessageSendParams messageSendParams, CancellationToken cancellationToken)
    {
        var contextId = messageSendParams.Message.ContextId!;
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
        if (response.Status == RequestStatus.Completed)
        {
            return response.ToMessage();
        }

        if (response.Status == RequestStatus.Failed)
        {
            throw new A2AException($"The agent request failed: {response.Data}");
        }

        // something wrong happened - we should not be here
        throw new A2AException($"The agent request reached unexpected state: {response.Data}");
    }

    public Task<AgentCard> GetAgentCardAsync(string agentPath, CancellationToken cancellationToken = default)
    {
        if (cancellationToken.IsCancellationRequested)
        {
            return Task.FromCanceled<AgentCard>(cancellationToken);
        }

        return Task.FromResult(new AgentCard()
        {
            Name = this._innerAgent.Name ?? string.Empty,
            Description = this._innerAgent.Description ?? string.Empty,
            Url = agentPath,
            Version = this._innerAgent.Id,
            DefaultInputModes = ["text"],
            DefaultOutputModes = ["text"],
            Capabilities = new()
            {
                Streaming = true,
                PushNotifications = false,
            },
            Skills = [],
        });
    }

    private ActorType GetActorType()
    {
        // agent is registered in DI via name
        ArgumentException.ThrowIfNullOrEmpty(this._innerAgent.Name);
        return new ActorType(this._innerAgent.Name);
    }
}
