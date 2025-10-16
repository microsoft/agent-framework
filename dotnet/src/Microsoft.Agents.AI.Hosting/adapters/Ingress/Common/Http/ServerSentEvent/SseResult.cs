using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Threading.Tasks.Dataflow;

using Azure.AI.AgentsHosting.Ingress.Common.Http.Json;

using Microsoft.AspNetCore.Http;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.ServerSentEvent;

/// <summary>
/// Represents a Server-Sent Events (SSE) result for ASP.NET Core.
/// </summary>
/// <param name="source">The source of SSE frames.</param>
/// <param name="keepAliveInterval">The keep-alive interval.</param>
public sealed class SseResult(
    IAsyncEnumerable<SseFrame> source,
    TimeSpan? keepAliveInterval = null)
    : IResult, IStatusCodeHttpResult, IContentTypeHttpResult
{
    private static readonly SseFrame s_keepAliveFrame = new()
    {
        Comments = ["keep-alive"]
    };

    private static readonly string s_keepAliveString = SerializeFrame(s_keepAliveFrame);

    private readonly TimeSpan _keepAliveInterval = keepAliveInterval ?? TimeSpan.FromSeconds(15);

    /// <inheritdoc/>
    public int? StatusCode => StatusCodes.Status200OK;

    /// <inheritdoc/>
    public string? ContentType => "text/event-stream; charset=utf-8";

    /// <inheritdoc/>
    public async Task ExecuteAsync(HttpContext httpContext)
    {
        var res = httpContext.Response;
        var ct = httpContext.RequestAborted;

        res.StatusCode = this.StatusCode!.Value;
        res.ContentType = this.ContentType!;
        res.Headers.CacheControl = "no-cache";
        res.Headers["X-Accel-Buffering"] = "no";
        res.Headers.Connection = "keep-alive";

        // generate fast and send event sequentially with backpressure
        var sseWritingQueue = new ActionBlock<string>(async frameStr =>
        {
            await res.WriteAsync(frameStr, ct).ConfigureAwait(false);
            await res.Body.FlushAsync(ct).ConfigureAwait(false);
        }, new ExecutionDataflowBlockOptions
        {
            MaxDegreeOfParallelism = 1,
            BoundedCapacity = 256,
            CancellationToken = ct,
        });

        var json = httpContext.GetJsonSerializerOptions();
        await res.StartAsync(ct).ConfigureAwait(false);
        await foreach (var frame in this.GetSourceWithKeepAliveAsync(ct).ConfigureAwait(false))
        {
            var frameStr = frame == s_keepAliveFrame ? s_keepAliveString : SerializeFrame(frame, json);
            if (!string.IsNullOrEmpty(frameStr))
            {
                await sseWritingQueue.SendAsync(frameStr, ct).ConfigureAwait(false);
            }
        }

        sseWritingQueue.Complete();
        await sseWritingQueue.Completion.ConfigureAwait(false);
    }

    private async IAsyncEnumerable<SseFrame> GetSourceWithKeepAliveAsync([EnumeratorCancellation] CancellationToken ct)
    {
#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await using var src = source.GetAsyncEnumerator(ct);
#pragma warning restore CA2007
        var fetching = src.MoveNextAsync().AsTask();

        while (true)
        {
            var timeout = false;
            try
            {
                if (!await fetching.WaitAsync(this._keepAliveInterval, ct).ConfigureAwait(false))
                {
                    yield break;
                }
            }
            catch (TimeoutException)
            {
                timeout = true;
            }

            if (timeout)
            {
                yield return s_keepAliveFrame;
                continue;
            }
            yield return src.Current!;
            fetching = src.MoveNextAsync().AsTask();
        }
    }

    private static string SerializeFrame(SseFrame frame, JsonSerializerOptions? json = null)
    {
        var sb = new StringBuilder();
        if (!string.IsNullOrEmpty(frame.Id))
        {
            sb.Append("id: ").Append(frame.Id).Append('\n');
        }

        if (!string.IsNullOrEmpty(frame.Name))
        {
            sb.Append("event: ").Append(frame.Name).Append('\n');
        }

        if (json != null && frame.Data?.Count > 0)
        {
#pragma warning disable IL2026, IL3050 // JSON serialization requires dynamic access
            foreach (var data in frame.Data)
            {
                var line = JsonSerializer.Serialize(data, json);
                sb.Append("data: ").Append(line).Append('\n');
            }
#pragma warning restore IL2026, IL3050
        }

        if (frame.Comments?.Count > 0)
        {
            foreach (var comment in frame.Comments)
            {
                sb.Append(": ").Append(comment).Append('\n');
            }
        }

        if (sb.Length <= 0)
        {
            return string.Empty;
        }

        sb.Append('\n');
        return sb.ToString();
    }
}
