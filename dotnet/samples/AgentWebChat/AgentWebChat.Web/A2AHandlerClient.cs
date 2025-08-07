// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using A2A;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.Web;

public class A2AHandlerClient
{
    private readonly ILogger _logger;
    private readonly Uri _uri;

    // because A2A sdk does not provide a client which can handle multiple agents, we need a client per agent
    // for this app the convention is "baseUri/<agentname>"
    private readonly ConcurrentDictionary<string, (A2AClient, A2ACardResolver)> _clients = new();

    public A2AHandlerClient(ILogger logger, Uri baseUri)
    {
        this._logger = logger;
        this._uri = baseUri;
    }

    public Task<AgentCard> GetAgentCardAsync(string agent, CancellationToken cancellationToken = default)
    {
        this._logger.LogInformation("Retrieving agent card for {Agent}", agent);

        var (_, a2aCardResolver) = this.ResolveClient(agent);
        return a2aCardResolver.GetAgentCardAsync(cancellationToken);
    }

    public Task<A2AResponse> SendMessageAsync(string agent, ActorRequest request, CancellationToken cancellationToken)
    {
        this._logger.LogInformation("Sending message for agent '{Agent}'", agent);

        var (a2aClient, _) = this.ResolveClient(agent);
        var sendParams = new MessageSendParams
        {
            Message = new()
            {
                Role = MessageRole.User,
                MessageId = Guid.NewGuid().ToString(),
                Parts = [ new TextPart { Text = request. }
                ]
            };
        };

        return a2aClient.SendMessageAsync(sendParams, cancellationToken);
    }

    private (A2AClient, A2ACardResolver) ResolveClient(string agentName)
    {
        return this._clients.GetOrAdd(agentName, name =>
        {
            var uri = new Uri($"{this._uri}/{name}/");
            var a2aClient = new A2AClient(uri);

            // /v1/card is a default path for A2A agent card discovery
            var a2aCardResolver = new A2ACardResolver(uri, agentCardPath: "/v1/card/");

            this._logger.LogInformation("Built clients for agent {Agent} with baseUri {Uri}", name, uri);
            return (a2aClient, a2aCardResolver);
        });
    }
}
