// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using Demo.DeclarativeWorkflow;

namespace DeclarativeWorkflow;

internal sealed class HttpInterceptor(StreamWriter eventWriter)
{
    private string? _lastRequest;

    public async ValueTask OnResponseAsync(HttpResponseIntercept intercept)
    {
        string currentRequest = $"{intercept.RequestMethod} {intercept.RequestUri}";

        if (currentRequest != this._lastRequest)
        {
            this._lastRequest = currentRequest;
            await eventWriter.WriteLineAsync($"{Environment.NewLine}{intercept.RequestMethod} {intercept.RequestUri}");
        }

        if (intercept.ResponseContent is not null)
        {
            await eventWriter.WriteAsync(intercept.ResponseContent);
        }

        await eventWriter.FlushAsync();
    }
}
