// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.Net.ServerSentEvents;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// IResult implementation for streaming JSON data using Server-Sent Events (SSE).
/// </summary>
/// <typeparam name="T">The type of items to stream.</typeparam>
internal sealed class SseJsonResult<T> : IResult
{
    private readonly IAsyncEnumerable<T> _events;
    private readonly JsonTypeInfo<T> _jsonTypeInfo;
    private readonly Func<T, string?> _getEventType;

    /// <summary>
    /// Initializes a new instance of the <see cref="SseJsonResult{T}"/> class.
    /// </summary>
    /// <param name="events">The async enumerable of items to stream.</param>
    /// <param name="getEventType">A function to get the optional event type from each item.</param>
    /// <param name="jsonTypeInfo">The JSON type information for serializing items.</param>
    public SseJsonResult(IAsyncEnumerable<T> events, Func<T, string?> getEventType, JsonTypeInfo<T> jsonTypeInfo)
    {
        this._events = events ?? throw new ArgumentNullException(nameof(events));
        this._jsonTypeInfo = jsonTypeInfo ?? throw new ArgumentNullException(nameof(jsonTypeInfo));
        this._getEventType = getEventType ?? throw new ArgumentNullException(nameof(getEventType));
    }

    /// <summary>
    /// Executes the result by streaming items to the HTTP response using Server-Sent Events format.
    /// </summary>
    /// <param name="httpContext">The HTTP context.</param>
    public async Task ExecuteAsync(HttpContext httpContext)
    {
        var response = httpContext.Response;
        var cancellationToken = httpContext.RequestAborted;

        // Set SSE headers
        response.Headers.ContentType = "text/event-stream";
        response.Headers.CacheControl = "no-cache,no-store";
        response.Headers.Connection = "keep-alive";
        response.Headers.ContentEncoding = "identity";
        httpContext.Features.GetRequiredFeature<IHttpResponseBodyFeature>().DisableBuffering();

        await SseFormatter.WriteAsync(
            source: this.GetItemsAsync(),
            destination: response.Body,
            itemFormatter: this.FormatItem,
            cancellationToken).ConfigureAwait(false);
    }

    private async IAsyncEnumerable<SseItem<T>> GetItemsAsync()
    {
        await foreach (var item in this._events.ConfigureAwait(false))
        {
            yield return new SseItem<T>(item, this._getEventType(item));
        }
    }

    private void FormatItem(SseItem<T> sseItem, IBufferWriter<byte> bufferWriter)
    {
        using var writer = new Utf8JsonWriter(bufferWriter);
        JsonSerializer.Serialize(writer, sseItem.Data, this._jsonTypeInfo);
        writer.Flush();
    }
}
