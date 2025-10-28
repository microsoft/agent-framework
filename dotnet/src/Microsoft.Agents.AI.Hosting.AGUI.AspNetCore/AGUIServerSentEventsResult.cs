// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal sealed class AGUIServerSentEventsResult : IResult
{
    private static readonly ReadOnlyMemory<byte> s_data = "data: "u8.ToArray().AsMemory();
    private static readonly ReadOnlyMemory<byte> s_newLines = "\n\n"u8.ToArray().AsMemory();

    private readonly IAsyncEnumerable<BaseEvent> _events;

    public int? StatusCode => StatusCodes.Status200OK;

    internal AGUIServerSentEventsResult(IAsyncEnumerable<BaseEvent> events)
    {
        this._events = events;
    }

    public async Task ExecuteAsync(HttpContext httpContext)
    {
        if (httpContext == null)
        {
            throw new ArgumentNullException(nameof(httpContext));
        }

        httpContext.Response.ContentType = "text/event-stream";
        httpContext.Response.Headers.CacheControl = "no-cache,no-store";
        httpContext.Response.Headers.Pragma = "no-cache";

        var body = httpContext.Response.Body;
        var cancellationToken = httpContext.RequestAborted;

        await foreach (var item in this._events.ConfigureAwait(false))
        {
            await body.WriteAsync(s_data, cancellationToken).ConfigureAwait(false);
            await JsonSerializer.SerializeAsync(
                body,
                item,
                AGUIJsonSerializerContext.Default.BaseEvent, cancellationToken).ConfigureAwait(false);
            await body.WriteAsync(s_newLines, cancellationToken).ConfigureAwait(false);
            await body.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        await body.FlushAsync(httpContext.RequestAborted).ConfigureAwait(false);
    }
}
