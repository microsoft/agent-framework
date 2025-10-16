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

/// <summary>
/// Extension methods for converting to SSE results.
/// </summary>
public static class SseResultExtensions
{
    /// <summary>
    /// Converts an async enumerable to an SSE result.
    /// </summary>
    /// <typeparam name="T">The source type.</typeparam>
    /// <param name="source">The async enumerable source.</param>
    /// <param name="frameTransformer">Function to transform items to SSE frames.</param>
    /// <param name="logger">The logger.</param>
    /// <param name="keepAliveInterval">The keep-alive interval.</param>
    /// <param name="ct">The cancellation token.</param>
    /// <returns>An SSE result.</returns>
    public static SseResult ToSseResult<T>(this IAsyncEnumerable<T> source, Func<T, SseFrame> frameTransformer,
        ILogger logger,
        TimeSpan? keepAliveInterval = null,
        CancellationToken ct = default)
    {
        var frames = TransformToSseFramesAsync(source, frameTransformer, logger, ct);
        return new SseResult(frames, keepAliveInterval);
    }

    private static async IAsyncEnumerable<SseFrame> TransformToSseFramesAsync<T>(this IAsyncEnumerable<T> source,
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
    /// <summary>
    /// Converts response stream events to an SSE result.
    /// </summary>
    /// <param name="source">The response stream events.</param>
    /// <param name="selector">Function to select SSE frames from events.</param>
    /// <param name="keepAliveInterval">The keep-alive interval.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>An SSE result.</returns>
    public static SseResult ToSseResult(
        this IAsyncEnumerable<ResponseStreamEvent> source,
        Func<ResponseStreamEvent, SseFrame> selector,
        TimeSpan? keepAliveInterval = null,
        CancellationToken cancellationToken = default)
        => new(source.ToSseFramesAsync(selector, cancellationToken), keepAliveInterval);

    private static async IAsyncEnumerable<SseFrame> ToSseFramesAsync(
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
