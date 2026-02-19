// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized;

internal sealed class AIContentExternalHandler<TRequestContent, TResponseContent>
    where TRequestContent : AIContent
    where TResponseContent : AIContent
{
    private readonly PortBinding? _portBinding;
    private ConcurrentDictionary<string, TRequestContent> _pendingRequests = new();

    public AIContentExternalHandler(ref ProtocolBuilder protocolBuilder, string portId, bool intercepted, Func<TResponseContent, IWorkflowContext, CancellationToken, ValueTask> handler)
    {
        PortBinding? portBinding = null;
        protocolBuilder = protocolBuilder.ConfigureRoutes(routeBuilder => ConfigureRoutes(routeBuilder, out portBinding));
        this._portBinding = portBinding;

        if (intercepted)
        {
            protocolBuilder = protocolBuilder.SendsMessage<TRequestContent>();
        }

        void ConfigureRoutes(RouteBuilder routeBuilder, out PortBinding? portBinding)
        {
            if (intercepted)
            {
                portBinding = null;
                routeBuilder.AddHandler(handler);
            }
            else
            {
                routeBuilder.AddPortHandler<TRequestContent, TResponseContent>(portId, handler, out portBinding);
            }
        }
    }

    public bool HasPendingRequests => !this._pendingRequests.IsEmpty;

    public Task ProcessRequestContentsAsync(Dictionary<string, TRequestContent> requests, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        IEnumerable<Task> requestTasks = from string requestId in requests.Keys
                                         select this.ProcessRequestContentAsync(requestId, requests[requestId], context, cancellationToken)
                                                    .AsTask();

        return Task.WhenAll(requestTasks);
    }

    public ValueTask ProcessRequestContentAsync(string id, TRequestContent requestContent, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (!this._pendingRequests.TryAdd(id, requestContent))
        {
            throw new InvalidOperationException($"A pending request with ID '{id}' already exists.");
        }

        return this.IsIntercepted
             ? context.SendMessageAsync(requestContent, cancellationToken: cancellationToken)
             : this._portBinding.PostRequestAsync(requestContent, id, cancellationToken);
    }

    public bool MarkRequestAsHandled(string id)
    {
        return this._pendingRequests.TryRemove(id, out _);
    }

    [MemberNotNullWhen(false, nameof(_portBinding))]
    private bool IsIntercepted => this._portBinding == null;

    private static string MakeKey(string id) => $"{id}_PendingRequests";

    public async ValueTask OnCheckpointingAsync(string id, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Dictionary<string, TRequestContent> pendingRequestsCopy = new(this._pendingRequests);
        await context.QueueStateUpdateAsync(MakeKey(id), pendingRequestsCopy, cancellationToken: cancellationToken)
                     .ConfigureAwait(false);
    }

    public async ValueTask OnCheckpointRestoredAsync(string id, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        Dictionary<string, TRequestContent>? loadedState =
            await context.ReadStateAsync<Dictionary<string, TRequestContent>>(MakeKey(id), cancellationToken: cancellationToken)
                         .ConfigureAwait(false);

        if (loadedState != null)
        {
            this._pendingRequests = new ConcurrentDictionary<string, TRequestContent>(loadedState);
        }
    }
}
