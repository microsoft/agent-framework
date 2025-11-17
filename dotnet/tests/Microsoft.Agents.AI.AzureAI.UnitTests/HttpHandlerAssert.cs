// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AzureAI.UnitTests;

internal sealed class HttpHandlerAssert : HttpClientHandler
{
    private readonly Func<HttpRequestMessage, HttpResponseMessage>? _assertion;
    private readonly Func<HttpRequestMessage, Task<HttpResponseMessage>>? _assertionAsync;

    public HttpHandlerAssert(Func<HttpRequestMessage, HttpResponseMessage> assertion)
    {
        this._assertion = assertion;
    }
    public HttpHandlerAssert(Func<HttpRequestMessage, Task<HttpResponseMessage>> assertionAsync)
    {
        this._assertionAsync = assertionAsync;
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (this._assertionAsync is not null)
        {
            return await this._assertionAsync.Invoke(request);
        }

        return this._assertion!.Invoke(request);
    }

#if NET
    protected override HttpResponseMessage Send(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        return this._assertion!(request);
    }
#endif
}
