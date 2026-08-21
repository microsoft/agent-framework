// Copyright (c) Microsoft. All rights reserved.

#if !NET10_0_OR_GREATER

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AGUI.Abstractions;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Streams an <see cref="IAsyncEnumerable{BaseEvent}"/> to the client as a Server-Sent Events
/// response. Polyfill for <c>TypedResults.ServerSentEvents</c> on target frameworks older than
/// net10.0; on net10.0+ the framework API is used directly from
/// <see cref="AGUIEndpointRouteBuilderExtensions"/>.
/// </summary>
internal sealed partial class AGUIServerSentEventsResult : IResult, IDisposable
{
    private readonly IAsyncEnumerable<BaseEvent> _events;
    private readonly ILogger<AGUIServerSentEventsResult> _logger;
    private Utf8JsonWriter? _jsonWriter;

    internal AGUIServerSentEventsResult(IAsyncEnumerable<BaseEvent> events, ILogger<AGUIServerSentEventsResult> logger)
    {
        this._events = events;
        this._logger = logger;
    }

    public async Task ExecuteAsync(HttpContext httpContext)
    {
        ArgumentNullException.ThrowIfNull(httpContext);

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
            LogStreamingError(this._logger, ex);
            try
            {
                var errorEvent = new RunErrorEvent
                {
                    Code = "StreamingError",

                    // Do not surface the raw exception message to the client; it can leak internal
                    // details. The full exception is recorded server-side via LogStreamingError above.
                    Message = "An error occurred while streaming the agent response.",
                };
                await SseFormatter.WriteAsync(
                    WrapEventsAsSseItemsAsync([errorEvent]),
                    body,
                    this.SerializeEvent,
                    CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception sendErrorEx)
            {
                LogSendErrorEventFailed(this._logger, sendErrorEx);
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

        await Task.CompletedTask.ConfigureAwait(false);
    }

    private void SerializeEvent(SseItem<BaseEvent> item, IBufferWriter<byte> writer)
    {
        if (this._jsonWriter is null)
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

    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "An error occurred while streaming AG-UI events",
        SkipEnabledCheck = true)]
    private static partial void LogStreamingError(ILogger logger, Exception exception);

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Failed to send error event to client after streaming failure",
        SkipEnabledCheck = true)]
    private static partial void LogSendErrorEventFailed(ILogger logger, Exception exception);
}

#endif
