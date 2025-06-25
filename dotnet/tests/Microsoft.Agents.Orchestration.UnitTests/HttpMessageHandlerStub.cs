// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Mime;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.Orchestration.UnitTest;

internal sealed class HttpMessageHandlerStub : HttpMessageHandler
{
    private static readonly HttpResponseMessage s_defaultResponse = new(HttpStatusCode.OK)
    {
        Content = new StringContent("{}", Encoding.UTF8, MediaTypeNames.Application.Json),
    };

    public HttpRequestHeaders? RequestHeaders { get; private set; }

    public HttpContentHeaders? ContentHeaders { get; private set; }

    public byte[]? RequestContent { get; private set; }

    public Uri? RequestUri { get; private set; }

    public HttpMethod? Method { get; private set; }

    public Queue<HttpResponseMessage> ResponseQueue { get; } = new();

    public byte[]? FirstMultipartContent { get; private set; }

#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
    protected override HttpResponseMessage Send(HttpRequestMessage request, CancellationToken cancellationToken) =>
        this.SendAsync(request, cancellationToken).GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Avoid problematic synchronous waits

    protected async override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        this.Method = request.Method;
        this.RequestUri = request.RequestUri;
        this.RequestHeaders = request.Headers;
        this.RequestContent = request.Content is null ? null : await request.Content.ReadAsByteArrayAsync(cancellationToken);

        if (request.Content is MultipartContent multipartContent)
        {
            this.FirstMultipartContent = await multipartContent.First().ReadAsByteArrayAsync(cancellationToken);
        }

        this.ContentHeaders = request.Content?.Headers;

        return
            //(this.ResponseQueue.Count == 0) ?
            //    s_defaultResponse :
                this.ResponseQueue.Dequeue();
    }
}
