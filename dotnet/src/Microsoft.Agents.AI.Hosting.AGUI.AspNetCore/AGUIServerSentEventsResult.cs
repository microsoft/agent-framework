// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal sealed class AGUIServerSentEventsResult : IResult, IDisposable
{
    private readonly IAsyncEnumerable<BaseEvent> _events;
    private Utf8JsonWriter? _jsonWriter;

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

        try
        {
            await SseFormatter.WriteAsync(
                WrapEventsAsSseItemsAsync(this._events, cancellationToken),
                body,
                this.SerializeEvent,
                cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // If an error occurs during streaming, try to send an error event before closing
            try
            {
                var errorEvent = new RunErrorEvent
                {
                    Code = "StreamingError",
                    Message = ex.Message
                };
                await SseFormatter.WriteAsync(
                    WrapEventsAsSseItemsAsync([errorEvent]),
                    body,
                    this.SerializeEvent,
                    CancellationToken.None).ConfigureAwait(false);
            }
            catch
            {
                // If we can't send the error event, just let the connection close
            }
        }

        await body.FlushAsync(httpContext.RequestAborted).ConfigureAwait(false);
    }

    private static async IAsyncEnumerable<SseItem<BaseEvent>> WrapEventsAsSseItemsAsync(
        IAsyncEnumerable<BaseEvent> events,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (BaseEvent evt in events.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            yield return new SseItem<BaseEvent>(evt);
        }
    }

    private static async IAsyncEnumerable<SseItem<BaseEvent>> WrapEventsAsSseItemsAsync(
        IEnumerable<BaseEvent> events)
    {
        foreach (BaseEvent evt in events)
        {
            yield return new SseItem<BaseEvent>(evt);
        }
    }

    private void SerializeEvent(SseItem<BaseEvent> item, IBufferWriter<byte> writer)
    {
        if (this._jsonWriter == null)
        {
            this._jsonWriter = new Utf8JsonWriter(writer);
        }
        else
        {
            this._jsonWriter.Reset(writer);
        }
        JsonSerializer.Serialize(this._jsonWriter, item.Data, AGUIJsonSerializerContext.Default.BaseEvent);
    }

    public void Dispose()
    {
        this._jsonWriter?.Dispose();
    }
}
