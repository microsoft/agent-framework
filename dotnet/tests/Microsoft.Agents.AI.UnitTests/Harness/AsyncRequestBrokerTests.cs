// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AsyncRequestBroker{TResult}"/> class.
/// </summary>
public class AsyncRequestBrokerTests
{
    #region Constructor Tests

    /// <summary>
    /// Verify that a non-positive settled queue size is rejected.
    /// </summary>
    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public void Constructor_InvalidSettledQueueSize_Throws(int size)
    {
        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new AsyncRequestBroker<int>(size));
    }

    #endregion

    #region Resolve / Reject Tests

    /// <summary>
    /// Verify that Resolve delivers the result to the waiter and clears the pending entry.
    /// </summary>
    [Fact]
    public async Task Resolve_DeliversResultToWaiterAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<string>();
        var task = broker.RequestAsync("req-1");
        Assert.Equal(1, broker.PendingCount);

        // Act
        bool resolved = broker.Resolve("req-1", "answer");

        // Assert
        Assert.True(resolved);
        Assert.Equal("answer", await task);
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that Reject delivers the exception to the waiter and clears the pending entry.
    /// </summary>
    [Fact]
    public async Task Reject_DeliversExceptionToWaiterAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<string>();
        var task = broker.RequestAsync("req-1");
        var error = new InvalidCastException("boom");

        // Act
        bool rejected = broker.Reject("req-1", error);

        // Assert
        Assert.True(rejected);
        var thrown = await Assert.ThrowsAsync<InvalidCastException>(() => task);
        Assert.Same(error, thrown);
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that resolving or rejecting an unknown ID returns false.
    /// </summary>
    [Fact]
    public void ResolveAndReject_UnknownId_ReturnFalse()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();

        // Act & Assert
        Assert.False(broker.Resolve("missing", 1));
        Assert.False(broker.Reject("missing", new InvalidOperationException()));
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that a late response for a recently resolved ID returns true, is ignored, and does not affect state.
    /// </summary>
    [Fact]
    public async Task ResolveAndReject_LateResponseForSettledId_ReturnTrueAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        var task = broker.RequestAsync("req-1");
        Assert.True(broker.Resolve("req-1", 1));
        Assert.Equal(1, await task);

        // Act
        bool lateResolve = broker.Resolve("req-1", 2);
        bool lateReject = broker.Reject("req-1", new InvalidOperationException());

        // Assert
        Assert.True(lateResolve);
        Assert.True(lateReject);
        Assert.Equal(1, await task);
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that null arguments are rejected.
    /// </summary>
    [Fact]
    public async Task NullArguments_ThrowAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => broker.RequestAsync(null!));
        Assert.Throws<ArgumentNullException>(() => broker.Resolve(null!, 1));
        Assert.Throws<ArgumentNullException>(() => broker.Reject(null!, new InvalidOperationException()));
        Assert.Throws<ArgumentNullException>(() => broker.Reject("req-1", null!));
        Assert.Equal(0, broker.PendingCount);
    }

    #endregion

    #region Duplicate ID Tests

    /// <summary>
    /// Verify that registering an ID that is already pending is rejected without disturbing the original waiter.
    /// </summary>
    [Fact]
    public async Task RequestAsync_DuplicatePendingId_ThrowsAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        var original = broker.RequestAsync("req-1");

        // Act
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("req-1"));

        // Assert
        Assert.Contains("already pending", ex.Message);
        Assert.Equal(1, broker.PendingCount);
        Assert.True(broker.Resolve("req-1", 42));
        Assert.Equal(42, await original);
    }

    /// <summary>
    /// Verify that registering a recently settled ID is rejected.
    /// </summary>
    [Fact]
    public async Task RequestAsync_SettledId_ThrowsAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        var task = broker.RequestAsync("req-1");
        broker.Resolve("req-1", 1);
        await task;

        // Act
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("req-1"));

        // Assert
        Assert.Contains("already settled", ex.Message);
        Assert.Equal(0, broker.PendingCount);
    }

    #endregion

    #region Timeout and Cancellation Tests

    /// <summary>
    /// Verify that an elapsed timeout cancels the waiter, clears the pending entry, and records the ID as settled.
    /// </summary>
    [Fact]
    public async Task RequestAsync_Timeout_CleansUpAndTracksSettledAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => broker.RequestAsync("req-1", TimeSpan.Zero));

        // Assert
        Assert.Equal(0, broker.PendingCount);
        Assert.True(broker.Resolve("req-1", 1));
        Assert.True(broker.Reject("req-1", new InvalidOperationException()));
        await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("req-1"));
    }

    /// <summary>
    /// Verify that cancelling the token cancels the waiter, clears the pending entry, and records the ID as settled.
    /// </summary>
    [Fact]
    public async Task RequestAsync_Cancellation_CleansUpAndTracksSettledAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        using var cts = new CancellationTokenSource();
        var task = broker.RequestAsync("req-1", cancellationToken: cts.Token);
        Assert.Equal(1, broker.PendingCount);

        // Act
        cts.Cancel();

        // Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.Equal(0, broker.PendingCount);
        Assert.True(broker.Resolve("req-1", 1));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("req-1"));
    }

    /// <summary>
    /// Verify that an already-cancelled token completes the request immediately and leaves no pending entry.
    /// </summary>
    [Fact]
    public async Task RequestAsync_PreCancelledToken_CleansUpAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => broker.RequestAsync("req-1", cancellationToken: cts.Token));
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that resolving before cancellation wins and the later cancellation has no effect.
    /// </summary>
    [Fact]
    public async Task RequestAsync_CancelAfterResolve_ReturnsResultAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        using var cts = new CancellationTokenSource();
        var task = broker.RequestAsync("req-1", cancellationToken: cts.Token);

        // Act
        Assert.True(broker.Resolve("req-1", 7));
        cts.Cancel();

        // Assert
        Assert.Equal(7, await task);
        Assert.Equal(0, broker.PendingCount);
    }

    /// <summary>
    /// Verify that an unsupported timeout is rejected before the request is registered.
    /// </summary>
    [Fact]
    public async Task RequestAsync_InvalidTimeout_ThrowsWithoutRegisteringAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => broker.RequestAsync("req-1", TimeSpan.FromMilliseconds(-5)));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => broker.RequestAsync("req-1", TimeSpan.FromMilliseconds((double)int.MaxValue + 1)));
        Assert.Equal(0, broker.PendingCount);

        // The ID must remain usable after the rejected attempts.
        var task = broker.RequestAsync("req-1");
        Assert.True(broker.Resolve("req-1", 3));
        Assert.Equal(3, await task);
    }

    /// <summary>
    /// Verify that <see cref="Timeout.InfiniteTimeSpan"/> is accepted and waits for a response.
    /// </summary>
    [Fact]
    public async Task RequestAsync_InfiniteTimeout_WaitsForResolveAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>();
        var task = broker.RequestAsync("req-1", Timeout.InfiniteTimeSpan);

        // Act
        Assert.True(broker.Resolve("req-1", 9));

        // Assert
        Assert.Equal(9, await task);
    }

    #endregion

    #region Settled Queue Eviction Tests

    /// <summary>
    /// Verify that the oldest settled ID is evicted once the bounded queue is full and can then be reused.
    /// </summary>
    [Fact]
    public async Task SettledQueue_EvictsOldestIdAsync()
    {
        // Arrange
        var broker = new AsyncRequestBroker<int>(settledQueueSize: 2);
        foreach (string id in new[] { "a", "b", "c" })
        {
            var task = broker.RequestAsync(id);
            broker.Resolve(id, 0);
            await task;
        }

        // Act
        bool evictedResolve = broker.Resolve("a", 1);
        bool evictedReject = broker.Reject("a", new InvalidOperationException());
        bool retainedResolve = broker.Resolve("b", 1);
        var reused = broker.RequestAsync("a");

        // Assert
        Assert.False(evictedResolve);
        Assert.False(evictedReject);
        Assert.True(retainedResolve);
        Assert.Equal(1, broker.PendingCount);
        await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("b"));
        await Assert.ThrowsAsync<InvalidOperationException>(() => broker.RequestAsync("c"));
        Assert.True(broker.Resolve("a", 5));
        Assert.Equal(5, await reused);
    }

    #endregion

    #region Concurrency Tests

    /// <summary>
    /// Verify invariants under concurrent resolve, reject, cancellation, and duplicate registration:
    /// exactly one settlement determines the outcome, late responses are accepted, duplicate registrations are always rejected, and no entries leak.
    /// </summary>
    [Fact]
    public async Task ConcurrentSettlementAndRegistration_PreservesInvariantsAsync()
    {
        // Arrange
        const int Count = 500;
        var broker = new AsyncRequestBroker<int>(settledQueueSize: Count * 2);
        var ctsList = Enumerable.Range(0, Count).Select(_ => new CancellationTokenSource()).ToArray();
        var requests = Enumerable.Range(0, Count)
            .Select(i => broker.RequestAsync($"req-{i}", cancellationToken: ctsList[i].Token))
            .ToArray();
        Assert.Equal(Count, broker.PendingCount);

        var resolveAccepted = new bool[Count];
        var rejectAccepted = new bool[Count];
        var duplicates = new Task<int>[Count];

        // Act
        await Task.WhenAll(Enumerable.Range(0, Count).Select(i => Task.WhenAll(
            Task.Run(() => resolveAccepted[i] = broker.Resolve($"req-{i}", i)),
            Task.Run(() => rejectAccepted[i] = broker.Reject($"req-{i}", new InvalidOperationException("rejected"))),
            Task.Run(() => ctsList[i].Cancel()),
            // Cast to Action so Task.Run does not unwrap (and await) the duplicate request task.
            Task.Run((Action)(() => duplicates[i] = broker.RequestAsync($"req-{i}"))))));

        // Assert
        Assert.Equal(0, broker.PendingCount);
        for (int i = 0; i < Count; i++)
        {
            // The ID was always either pending or recently settled, so both responses are accepted
            // (the one that loses the race is ignored as a late response).
            Assert.True(resolveAccepted[i]);
            Assert.True(rejectAccepted[i]);

            // Exactly one settlement (resolve, reject, or cancel) determines the outcome.
            var request = requests[i];
            await Task.WhenAny(request);
            if (request.Status == TaskStatus.RanToCompletion)
            {
                Assert.Equal(i, await request);
            }
            else if (request.IsCanceled)
            {
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => request);
            }
            else
            {
                await Assert.ThrowsAsync<InvalidOperationException>(() => request);
            }

            // The ID was always either pending or settled, so the duplicate registration must have been rejected.
            await Assert.ThrowsAsync<InvalidOperationException>(() => duplicates[i]);
            ctsList[i].Dispose();
        }
    }

    #endregion
}
