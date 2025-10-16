using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace Azure.AI.AgentsHosting.Ingress.Common;

/// <summary>
/// Extension methods for IAsyncEnumerable.
/// </summary>
public static class AsyncEnumerableExtensions
{
    /// <summary>
    /// Chunks the source based on when items change.
    /// </summary>
    /// <typeparam name="TSource">The source item type.</typeparam>
    /// <param name="source">The async enumerable source.</param>
    /// <param name="isChanged">Function to determine if items changed.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>Chunked async enumerable.</returns>
    public static IAsyncEnumerable<IAsyncEnumerable<TSource>> ChunkOnChangeAsync<TSource>(
        this IAsyncEnumerable<TSource> source,
        Func<TSource?, TSource?, bool>? isChanged = null,
        CancellationToken cancellationToken = default)
    {
        var c = isChanged == null
            ? EqualityComparer<TSource>.Default
            : EqualityComparer<TSource>.Create((x, y) => !isChanged(x, y), t => t?.GetHashCode() ?? 0);

        return source.ChunkByKeyAsync(x => x, c, cancellationToken);
    }

    /// <summary>
    /// Chunks the source by key selector.
    /// </summary>
    /// <typeparam name="TSource">The source item type.</typeparam>
    /// <typeparam name="TKey">The key type.</typeparam>
    /// <param name="source">The async enumerable source.</param>
    /// <param name="keySelector">Function to select the key.</param>
    /// <param name="comparer">Optional key comparer.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>Chunked async enumerable by key.</returns>
    public static async IAsyncEnumerable<IAsyncEnumerable<TSource>> ChunkByKeyAsync<TSource, TKey>(
        this IAsyncEnumerable<TSource> source,
        Func<TSource, TKey> keySelector,
        IEqualityComparer<TKey>? comparer = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        comparer ??= EqualityComparer<TKey>.Default;

#pragma warning disable CA2007 // Consider calling ConfigureAwait on the awaited task
        await using var e = source.GetAsyncEnumerator(cancellationToken);
#pragma warning restore CA2007
        if (!await e.MoveNextAsync().ConfigureAwait(false))
        {
            yield break;
        }

        var pending = e.Current;
        var pendingKey = keySelector(pending);
        var hasPending = true;

        while (hasPending)
        {
            var currentKey = pendingKey;

            yield return InnerAsync(cancellationToken);
            continue;

            [SuppressMessage("ReSharper", "AccessToDisposedClosure")]
            async IAsyncEnumerable<TSource> InnerAsync([EnumeratorCancellation] CancellationToken ct = default)
            {
                ct.ThrowIfCancellationRequested();
                yield return pending; // first of the group

                while (await e.MoveNextAsync().ConfigureAwait(false))
                {
                    ct.ThrowIfCancellationRequested();

                    var item = e.Current;
                    var k = keySelector(item);

                    if (!comparer.Equals(k, currentKey))
                    {
                        // Hand the first item of the next group back to the outer loop
                        pending = item;
                        pendingKey = k;
                        yield break;
                    }

                    yield return item;
                }

                // source ended; tell the outer loop to stop after this group
                hasPending = false;
            }
        }
    }

    /// <summary>
    /// Peeks at the first item of an async enumerable without consuming it.
    /// </summary>
    /// <typeparam name="T">The item type.</typeparam>
    /// <param name="source">The async enumerable source.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A tuple indicating if there's a value, the first item, and the source.</returns>
    public static async ValueTask<(bool HasValue, T First, IAsyncEnumerable<T> Source)> PeekAsync<T>(
        this IAsyncEnumerable<T> source,
        CancellationToken cancellationToken = default)
    {
        var e = source.GetAsyncEnumerator(cancellationToken);
        var moveNextSucceeded = false;
        try
        {
            moveNextSucceeded = await e.MoveNextAsync().ConfigureAwait(false);
            if (!moveNextSucceeded)
            {
                return (false, default!, EmptyAsync<T>());
            }
        }
        finally
        {
            if (!moveNextSucceeded)
            {
                await e.DisposeAsync().ConfigureAwait(false);
            }
        }

        var first = e.Current;

        return (true, first, SequenceAsync(first, e));

        static async IAsyncEnumerable<T> SequenceAsync(T first, IAsyncEnumerator<T> e)
        {
            try
            {
                yield return first;
                while (await e.MoveNextAsync().ConfigureAwait(false))
                {
                    yield return e.Current;
                }
            }
            finally
            {
                await e.DisposeAsync().ConfigureAwait(false);
            }
        }
    }

#pragma warning disable CS1998
    private static async IAsyncEnumerable<T> EmptyAsync<T>()
    {
        yield break;
    }
#pragma warning restore CS1998
}
