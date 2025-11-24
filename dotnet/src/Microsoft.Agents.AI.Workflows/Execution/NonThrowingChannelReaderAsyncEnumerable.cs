// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

/// <summary>
/// A custom IAsyncEnumerable implementation that reads from a ChannelReader,
/// and suppresses OperationCanceledException when the cancellation token is triggered.
/// </summary>
internal sealed class NonThrowingChannelReaderAsyncEnumerable<T>(ChannelReader<T> reader) : IAsyncEnumerable<T>
{
    private class Enumerator(ChannelReader<T> reader, CancellationToken cancellationToken) : IAsyncEnumerator<T>
    {
        public T Current { get => field ?? throw new InvalidOperationException("Enumeration not started."); private set; }

        public ValueTask DisposeAsync()
        {
            // no-op - the reader should not be disposed.
            return default;
        }

        /// <summary>
        /// Moves to the next item in the channel.
        /// </summary>
        /// <returns>If successful, returns <c>true</c>, otherwise <c>false</c>.</returns>
        public async ValueTask<bool> MoveNextAsync()
        {
            try
            {
                bool hasData = await reader.WaitToReadAsync(cancellationToken).ConfigureAwait(false);
                if (hasData)
                {
                    this.Current = await reader.ReadAsync(cancellationToken).ConfigureAwait(false);
                    return true;
                }
            }
            catch (OperationCanceledException)
            {
                // Swallow cancellation exceptions to prevent throwing from the enumerator
                // Enables clean cancellation and aligns with the expected behavior of IAsyncEnumerable.
            }

            return false;
        }
    }

    /// <summary>
    /// Returns an async enumerator that reads items from the channel.
    /// If cancellation is requested, the enumeration exits silently without throwing.
    /// </summary>
    /// <param name="cancellationToken">An optional cancellation token from the caller.</param>
    /// <returns>An async enumerator over the channel items.</returns>
    public IAsyncEnumerator<T> GetAsyncEnumerator(CancellationToken cancellationToken = default)
        => new Enumerator(reader, cancellationToken);
}
