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

public sealed class SseResult(
    IAsyncEnumerable<SseFrame> source,
    TimeSpan? keepAliveInterval = null)
    : IResult, IStatusCodeHttpResult, IContentTypeHttpResult
{
    private static readonly SseFrame KeepAliveFrame = new()
    {
        Comments = ["keep-alive"]
    };

    private static readonly string KeepAliveString = SerializeFrame(KeepAliveFrame);

    private readonly TimeSpan _keepAliveInterval = keepAliveInterval ?? TimeSpan.FromSeconds(15);

    public int? StatusCode => StatusCodes.Status200OK;
    public string? ContentType => "text/event-stream; charset=utf-8";

    public async Task ExecuteAsync(HttpContext ctx)
    {
        var res = ctx.Response;
        var ct = ctx.RequestAborted;

        res.StatusCode = StatusCode!.Value;
        res.ContentType = ContentType!;
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

        var json = ctx.GetJsonSerializerOptions();
        await res.StartAsync(ct).ConfigureAwait(false);
        await foreach (var frame in GetSourceWithKeepAlive(ct))
        {
            var frameStr = frame == KeepAliveFrame ? KeepAliveString : SerializeFrame(frame, json);
            if (!string.IsNullOrEmpty(frameStr))
            {
                await sseWritingQueue.SendAsync(frameStr, ct).ConfigureAwait(false);
            }
        }

        sseWritingQueue.Complete();
        await sseWritingQueue.Completion.ConfigureAwait(false);
    }

    private async IAsyncEnumerable<SseFrame> GetSourceWithKeepAlive([EnumeratorCancellation] CancellationToken ct)
    {
        await using var src = source.GetAsyncEnumerator(ct);
        var fetching = src.MoveNextAsync().AsTask();

        while (true)
        {
            var timeout = false;
            try
            {
                if (!await fetching.WaitAsync(_keepAliveInterval, ct).ConfigureAwait(false))
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
                yield return KeepAliveFrame;
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
            foreach (var data in frame.Data)
            {
                var line = JsonSerializer.Serialize(data, json);
                sb.Append("data: ").Append(line).Append('\n');
            }
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
