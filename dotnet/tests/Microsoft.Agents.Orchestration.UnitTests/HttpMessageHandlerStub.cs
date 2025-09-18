// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Orchestration.UnitTest;

internal sealed class HttpMessageHandlerStub : HttpMessageHandler
{
    public Queue<HttpResponseMessage> ResponseQueue { get; } = new();

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
        Task.FromResult(this.ResponseQueue.Dequeue());
}
