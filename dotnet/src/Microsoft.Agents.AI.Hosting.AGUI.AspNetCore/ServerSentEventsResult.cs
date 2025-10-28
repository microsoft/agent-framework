// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.IO;
using System.Net.ServerSentEvents;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal sealed class ServerSentEventsResult<T> : IResult
{
    private readonly IAsyncEnumerable<SseItem<T>> _events;

    public int? StatusCode => StatusCodes.Status200OK;

    internal ServerSentEventsResult(IAsyncEnumerable<SseItem<T>> events)
    {
        this._events = events;
    }

    public async Task ExecuteAsync(HttpContext httpContext)
    {
        if (httpContext == null)
        {
            throw new System.ArgumentNullException(nameof(httpContext));
        }

        httpContext.Response.ContentType = "text/event-stream";
        httpContext.Response.Headers.CacheControl = "no-cache,no-store";
        httpContext.Response.Headers.Pragma = "no-cache";

        Stream responseStream = httpContext.Response.Body;

        await foreach (SseItem<T> item in this._events.ConfigureAwait(false))
        {
            await WriteSseItemAsync(responseStream, item, httpContext.RequestAborted).ConfigureAwait(false);
        }

        await responseStream.FlushAsync(httpContext.RequestAborted).ConfigureAwait(false);
    }

    private static async Task WriteSseItemAsync(Stream stream, SseItem<T> item, System.Threading.CancellationToken cancellationToken)
    {
        if (!string.IsNullOrEmpty(item.EventType))
        {
            byte[] eventTypeBytes = Encoding.UTF8.GetBytes($"event: {item.EventType}\n");
            await stream.WriteAsync(eventTypeBytes, cancellationToken).ConfigureAwait(false);
        }

        if (item.Data is string stringData)
        {
            byte[] dataBytes = Encoding.UTF8.GetBytes($"data: {stringData}\n\n");
            await stream.WriteAsync(dataBytes, cancellationToken).ConfigureAwait(false);
        }
        else if (item.Data is not null)
        {
            string json = JsonSerializer.Serialize(item.Data, typeof(T), AGUIJsonSerializerContext.Default);
            byte[] dataBytes = Encoding.UTF8.GetBytes($"data: {json}\n\n");
            await stream.WriteAsync(dataBytes, cancellationToken).ConfigureAwait(false);
        }
    }
}
