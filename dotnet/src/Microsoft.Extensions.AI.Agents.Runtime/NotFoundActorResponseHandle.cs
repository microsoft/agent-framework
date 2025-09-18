// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

internal sealed class NotFoundActorResponseHandle : ActorResponseHandle
{
    private readonly ActorResponse _response;

    public NotFoundActorResponseHandle(ActorId actorId, string messageId)
    {
        this._response = new ActorResponse()
        {
            Status = RequestStatus.NotFound,
            ActorId = actorId,
            MessageId = messageId,
        };
    }

    public override ValueTask CancelAsync(CancellationToken cancellationToken) =>
        throw new InvalidOperationException(
            $"Failed to cancel request for actor '{this._response.ActorId}' with message ID '{this._response.MessageId}'. The request was not found.");

    public override ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken) =>
        new(this._response);

    public override bool TryGetResponse([NotNullWhen(true)] out ActorResponse? response)
    {
        response = this._response;
        return true;
    }

    public override async IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync([EnumeratorCancellation] CancellationToken cancellationToken)
    {
        yield break;
    }
}
