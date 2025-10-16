using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;

namespace Azure.AI.AgentsHosting.Ingress.Common;

public static class AsyncEnumerableExtensions
{
    public static IAsyncEnumerable<IAsyncEnumerable<TSource>> ChunkOnChange<TSource>(
        this IAsyncEnumerable<TSource> source,
        Func<TSource?, TSource?, bool>? isChanged = null,
        CancellationToken cancellationToken = default)
    {
        var c = isChanged == null
            ? EqualityComparer<TSource>.Default
            : EqualityComparer<TSource>.Create((x, y) => !isChanged(x, y), t => t?.GetHashCode() ?? 0);

        return source.ChunkByKey(x => x, c, cancellationToken);
    }

    public static async IAsyncEnumerable<IAsyncEnumerable<TSource>> ChunkByKey<TSource, TKey>(
        this IAsyncEnumerable<TSource> source,
        Func<TSource, TKey> keySelector,
        IEqualityComparer<TKey>? comparer = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        comparer ??= EqualityComparer<TKey>.Default;

        await using var e = source.GetAsyncEnumerator(cancellationToken);
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

            yield return Inner(cancellationToken);
            continue;

            [SuppressMessage("ReSharper", "AccessToDisposedClosure")]
            async IAsyncEnumerable<TSource> Inner([EnumeratorCancellation] CancellationToken ct = default)
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

    public static async ValueTask<(bool HasValue, T First, IAsyncEnumerable<T> Source)> Peek<T>(
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
                return (false, default!, Empty<T>());
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

        return (true, first, Sequence(first, e));

        static async IAsyncEnumerable<T> Sequence(T first, IAsyncEnumerator<T> e)
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
    private static async IAsyncEnumerable<T> Empty<T>()
    {
        yield break;
    }
#pragma warning restore CS1998
}
