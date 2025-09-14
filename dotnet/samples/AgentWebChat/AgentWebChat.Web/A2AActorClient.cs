// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using A2A;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents.Hosting;
using Microsoft.Extensions.AI.Agents.Hosting.A2A.Converters;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace AgentWebChat.Web;

internal sealed class A2AActorClient : IActorClient
{
    private readonly ILogger _logger;
    private readonly Uri _uri;

    // because A2A sdk does not provide a client which can handle multiple agents, we need a client per agent
    // for this app the convention is "baseUri/<agentname>"
    private readonly ConcurrentDictionary<string, (A2AClient, A2ACardResolver)> _clients = [];

    public A2AActorClient(ILogger logger, Uri baseUri)
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

    public ValueTask<ActorResponseHandle> GetResponseAsync(ActorId actorId, string messageId, CancellationToken cancellationToken) => throw new NotImplementedException();

    public ValueTask<ActorResponseHandle> SendRequestAsync(ActorRequest request, CancellationToken cancellationToken)
    {
        var agentName = request.ActorId.Type;
        var (a2aClient, _) = this.ResolveClient(agentName);

        return new ValueTask<ActorResponseHandle>(new A2AActorResponseHandle(a2aClient, request));
    }

    private (A2AClient, A2ACardResolver) ResolveClient(ActorType agentName)
        => this.ResolveClient(agentName.Name);

    private (A2AClient, A2ACardResolver) ResolveClient(string agentName) =>
        this._clients.GetOrAdd(agentName, name =>
        {
            var uri = new Uri($"{this._uri}/{name}/");
            var a2aClient = new A2AClient(uri);

            // /v1/card is a default path for A2A agent card discovery
            var a2aCardResolver = new A2ACardResolver(uri, agentCardPath: "/v1/card/");

            this._logger.LogInformation("Built clients for agent {Agent} with baseUri {Uri}", name, uri);
            return (a2aClient, a2aCardResolver);
        });

    private sealed class A2AActorResponseHandle : ActorResponseHandle
    {
        private readonly A2AClient _a2aClient;
        private readonly ActorRequest _request;

        public A2AActorResponseHandle(A2AClient a2aClient, ActorRequest request)
        {
            this._a2aClient = a2aClient;
            this._request = request;
        }

        public override ValueTask CancelAsync(CancellationToken cancellationToken) => throw new NotImplementedException();

        public override ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken) => throw new NotImplementedException();

        public override bool TryGetResponse([NotNullWhen(true)] out ActorResponse? response) => throw new NotImplementedException();

        public override async IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            var agentRunRequestData = this._request.Params.Deserialize(AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunRequest))) as AgentRunRequest;
            var messageTexts = agentRunRequestData!.Messages!.SelectMany(x => x.Contents.OfType<TextContent>()).Select(x => x.Text);
            var parts = messageTexts.Select(text => new TextPart { Text = text });
            var messageSendParams = new MessageSendParams
            {
                Message = new()
                {
                    Role = MessageRole.User,
                    MessageId = this._request.MessageId,
                    ContextId = this._request.ActorId.Key,
                    Parts = [.. parts]
                }
            };

            await foreach (var upd in this._a2aClient.SendMessageStreamAsync(messageSendParams, cancellationToken))
            {
                var @event = upd.Data;
                if (@event is not Message message)
                {
                    throw new NotSupportedException("Only message is supported in A2A processing, but got: " + @event.GetType());
                }

                // handling of message on agentProxy side expects the 
                yield return message.ToActorRequestUpdate(status: RequestStatus.Pending);
            }

            // complete request after all updates are sent
            yield return new ActorRequestUpdate(status: RequestStatus.Completed, data: default);
        }
    }
}
