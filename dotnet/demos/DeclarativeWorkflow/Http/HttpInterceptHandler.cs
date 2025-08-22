// Copyright (c) Microsoft. All rights reserved.

#if NET

using System;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Demo.DeclarativeWorkflow;

internal sealed record class HttpResponseIntercept(HttpMethod RequestMethod, Uri? RequestUri, string? ResponseContent);

internal sealed class HttpInterceptHandler : HttpClientHandler
{
    public Func<HttpResponseIntercept, ValueTask>? OnIntercept { get; set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        // Call the inner handler to process the request and get the response
        HttpResponseMessage response = await base.SendAsync(request, cancellationToken);

        // Intercept and modify the response
        if (response.Content != null)
        {
            response.Content = new StreamContent(new InterceptStream(await response.Content.ReadAsStreamAsync(cancellationToken), OnResponse));
        }

        return response;

        void OnResponse(byte[] buffer, int offset, int length)
        {
            if (this.OnIntercept is not null)
            {
                Encoding.UTF8.GetString(buffer, 0, length);
                string responseContent = Encoding.UTF8.GetString(buffer, offset, length);
                // Invoke the intercept callback if it is set
                ValueTask task = this.OnIntercept(new HttpResponseIntercept(request.Method, request.RequestUri, responseContent)); // %%% HAXX: CHANNEL (Lighter)
            }
        }
    }
}

#endif
