// <copyright file="SseResultExtensions.cs" company="Microsoft">
// Copyright (c) Microsoft. All rights reserved.
// </copyright>

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

using AzureAIAgents.Models;

using Microsoft.Extensions.Logging;

namespace Azure.AI.AgentsHosting.Ingress.Common.Http.ServerSentEvent;

public static class SseResultExtensions
{
    public static SseResult ToSseResult<T>(this IAsyncEnumerable<T> source, Func<T, SseFrame> frameTransformer,
        ILogger logger,
        CancellationToken ct = default,
        TimeSpan? keepAliveInterval = null)
    {
        var frames = TransformToSseFrames(source, frameTransformer, logger, ct);
        return new SseResult(frames, keepAliveInterval);
    }

    private static async IAsyncEnumerable<SseFrame> TransformToSseFrames<T>(this IAsyncEnumerable<T> source,
        Func<T, SseFrame> frameTransformer,
        ILogger logger,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        await foreach (var item in source.WithCancellation(ct))
        {
            yield return frameTransformer(item);
        }
        logger.LogInformation("Completed streaming response.");
    }

#if NET6_0_OR_GREATER
    public static SseResult ToSseResult(
        this IAsyncEnumerable<ResponseStreamEvent> source,
        Func<ResponseStreamEvent, SseFrame> selector,
        TimeSpan? keepAliveInterval = null,
        CancellationToken cancellationToken = default)
        => new(source.ToSseFrames(selector, cancellationToken), keepAliveInterval);

    private static async IAsyncEnumerable<SseFrame> ToSseFrames(
        this IAsyncEnumerable<ResponseStreamEvent> source,
        Func<ResponseStreamEvent, SseFrame> selector,
        [EnumeratorCancellation] CancellationToken ct = default)
    {
        await foreach (var item in source.WithCancellation(ct).ConfigureAwait(false))
        {
            yield return selector(item);
        }
    }
#endif
}
