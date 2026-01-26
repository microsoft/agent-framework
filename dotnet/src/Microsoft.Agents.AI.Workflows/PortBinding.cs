// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows;

internal class PortBinding(RequestPort port, IExternalRequestSink sink)
{
    public RequestPort Port => port;
    public IExternalRequestSink Sink => sink;

    public ValueTask PostRequestAsync<TRequest>(TRequest request, string? requestId = null, CancellationToken cancellationToken = default)
    {
        ExternalRequest externalRequest = ExternalRequest.Create(this.Port, request, requestId);
        return this.Sink.PostAsync(externalRequest);
    }
}
