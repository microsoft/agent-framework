// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests atomic cache creation and the lifetime of its synchronization state.
/// </summary>
public sealed class MemoryCacheExtensionsTests
{
    private static readonly TimeSpan s_gateTimeout = TimeSpan.FromSeconds(10);

    // The cache is disposed after all deliberately pending extension tasks have been drained in finally;
    // the analyzer cannot infer that synchronization from the test's gates.
#pragma warning disable CA2025
    /// <summary>Verifies that factory failure does not split queued and newly registered callers across locks.</summary>
    [Fact]
    public async Task GetOrCreateAtomicAsync_FailedOwnerDoesNotSplitQueuedCallersAsync()
    {
        // Arrange
        var cache = new MemoryCache(new MemoryCacheOptions());
        object key = new();
        var ownerFactoryEntered = NewSignal();
        var releaseOwnerFactory = NewSignal();
        var queuedWaiterFactoryEntered = NewSignal();
        var newCallerFactoryEntered = NewSignal();
        var releaseRetryFactory = NewSignal();
        var ownerFailure = new InvalidOperationException("The first factory attempt failed.");
        int factoryCallCount = 0;
        int activeFactoryCount = 0;
        int maxActiveFactoryCount = 0;

        object Factory(ICacheEntry _)
        {
            int call = Interlocked.Increment(ref factoryCallCount);
            int active = Interlocked.Increment(ref activeFactoryCount);
            UpdateMaximum(ref maxActiveFactoryCount, active);

            try
            {
                switch (call)
                {
                    case 1:
                        ownerFactoryEntered.TrySetResult(true);
                        releaseOwnerFactory.Task.WaitAsync(s_gateTimeout).GetAwaiter().GetResult();
                        throw ownerFailure;
                    case 2:
                        queuedWaiterFactoryEntered.TrySetResult(true);
                        releaseRetryFactory.Task.WaitAsync(s_gateTimeout).GetAwaiter().GetResult();
                        return new object();
                    case 3:
                        newCallerFactoryEntered.TrySetResult(true);
                        return new object();
                    default:
                        throw new InvalidOperationException("Unexpected factory invocation.");
                }
            }
            finally
            {
                Interlocked.Decrement(ref activeFactoryCount);
            }
        }

        Task<object>? owner = null;
        Task<object>? queuedWaiter = null;
        Task<object>? newCaller = null;

        try
        {
            owner = Task.Run(async () => await cache.GetOrCreateAtomicAsync(key, Factory).ConfigureAwait(false));
            await ownerFactoryEntered.Task.WaitAsync(s_gateTimeout);

            // The call executes synchronously through WaitAsync. Its pending return proves it queued on the
            // semaphore currently held by the first factory.
            queuedWaiter = cache.GetOrCreateAtomicAsync(key, Factory);
            Assert.False(queuedWaiter.IsCompleted);

            // Fail the first owner only after the waiter has queued on its semaphore.
            releaseOwnerFactory.TrySetResult(true);
            InvalidOperationException observedFailure = await Assert.ThrowsAsync<InvalidOperationException>(
                async () => await owner.WaitAsync(s_gateTimeout));
            Assert.Same(ownerFailure, observedFailure);
            await queuedWaiterFactoryEntered.Task.WaitAsync(s_gateTimeout);

            // Act: the queued waiter is now blocked in its retry factory. A new same-key caller must join that
            // same semaphore and remain pending until the retry completes.
            newCaller = cache.GetOrCreateAtomicAsync(key, Factory);

            // Assert: old waiters and new callers must share the lock even after its first factory fails.
            Assert.Equal(2, Volatile.Read(ref factoryCallCount));
            Assert.Equal(1, Volatile.Read(ref maxActiveFactoryCount));
            Assert.False(newCallerFactoryEntered.Task.IsCompleted);
            Assert.False(newCaller.IsCompleted);
        }
        finally
        {
            releaseOwnerFactory.TrySetResult(true);
            releaseRetryFactory.TrySetResult(true);
            if (owner is not null)
            {
                try
                {
                    await owner.WaitAsync(s_gateTimeout);
                }
                catch (InvalidOperationException)
                {
                    // The owner is expected to fail; await it before disposing the cache it used.
                }
                catch (TimeoutException)
                {
                    // Preserve the original assertion while bounding cleanup if the reproduction stalls.
                }
            }

            if (queuedWaiter is not null)
            {
                await queuedWaiter.WaitAsync(s_gateTimeout);
            }

            if (newCaller is not null)
            {
                await newCaller.WaitAsync(s_gateTimeout);
            }

            cache.Dispose();
        }

        object[] results = await Task.WhenAll(queuedWaiter!, newCaller!).WaitAsync(s_gateTimeout);
        Assert.Same(results[0], results[1]);
        Assert.Equal(2, Volatile.Read(ref factoryCallCount));
    }

    /// <summary>Verifies that canceling a waiter preserves the active factory holder's lock.</summary>
    [Fact]
    public async Task GetOrCreateAtomicAsync_CanceledWaiter_DoesNotReleaseActiveFactoryAsync()
    {
        // Arrange
        var cache = new MemoryCache(new MemoryCacheOptions());
        using CancellationTokenSource waiterCancellation = new();
        object key = new();
        object expectedValue = new();
        var ownerFactoryEntered = NewSignal();
        var releaseOwnerFactory = NewSignal();
        int factoryCallCount = 0;
        Task<object>? owner = null;
        Task<object>? healthyWaiter = null;

        object Factory(ICacheEntry entry)
        {
            Interlocked.Increment(ref factoryCallCount);
            ownerFactoryEntered.TrySetResult(true);
            releaseOwnerFactory.Task.WaitAsync(s_gateTimeout).GetAwaiter().GetResult();
            return expectedValue;
        }

        try
        {
            owner = Task.Run(async () => await cache.GetOrCreateAtomicAsync(key, Factory).ConfigureAwait(false));
            await ownerFactoryEntered.Task.WaitAsync(s_gateTimeout);
            Task<object> canceledWaiter = cache.GetOrCreateAtomicAsync(key, Factory, waiterCancellation.Token);
            Assert.False(canceledWaiter.IsCompleted);

            // Act
            waiterCancellation.Cancel();
            OperationCanceledException error = await Assert.ThrowsAnyAsync<OperationCanceledException>(
                async () => await canceledWaiter.WaitAsync(s_gateTimeout));
            healthyWaiter = cache.GetOrCreateAtomicAsync(key, Factory);

            // Assert: cancellation removes only the waiting caller's reference, without releasing the holder.
            Assert.Equal(waiterCancellation.Token, error.CancellationToken);
            Assert.False(healthyWaiter.IsCompleted);
            Assert.Equal(1, Volatile.Read(ref factoryCallCount));
        }
        finally
        {
            releaseOwnerFactory.TrySetResult(true);
            if (owner is not null)
            {
                await owner.WaitAsync(s_gateTimeout);
            }

            if (healthyWaiter is not null)
            {
                await healthyWaiter.WaitAsync(s_gateTimeout);
            }

            cache.Dispose();
        }

        Assert.Same(expectedValue, await owner!);
        Assert.Same(expectedValue, await healthyWaiter!);
        Assert.Equal(1, Volatile.Read(ref factoryCallCount));
    }
#pragma warning restore CA2025

    /// <summary>Verifies that a factory failure does not publish its partial entry value.</summary>
    [Fact]
    public async Task GetOrCreateAtomicAsync_FactorySetsValueThenThrows_DoesNotCachePartialValueAsync()
    {
        // Arrange
        using var cache = new MemoryCache(new MemoryCacheOptions());
        object key = new();
        var failure = new InvalidOperationException("Creation did not finish.");

        // Act
        InvalidOperationException observedFailure = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            cache.GetOrCreateAtomicAsync<object>(key, entry =>
            {
                entry.Value = new object();
                throw failure;
            }));

        // Assert
        Assert.Same(failure, observedFailure);
        Assert.False(cache.TryGetValue(key, out _));
    }

    /// <summary>Verifies that completed calls release the cache from static synchronization state.</summary>
    /// <param name="cancelBeforeCall">Whether the call is canceled before lock acquisition.</param>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void GetOrCreateAtomicAsync_CompletedCall_DoesNotRetainCache(bool cancelBeforeCall)
    {
        // Arrange / Act
        WeakReference cacheReference = CreateCompletedCacheCall(cancelBeforeCall);

        // Assert: completed and canceled calls must release the cache from the static synchronization state.
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        Assert.False(cacheReference.IsAlive);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static WeakReference CreateCompletedCacheCall(bool cancelBeforeCall)
    {
        using var cache = new MemoryCache(new MemoryCacheOptions());
        using CancellationTokenSource cancellation = new();
        if (cancelBeforeCall)
        {
            cancellation.Cancel();
        }

        // This call has no pending wait; assert completion before the cache and token source are disposed.
#pragma warning disable CA2025
        Task<object> operation = cache.GetOrCreateAtomicAsync(new object(), _ => new object(), cancellation.Token);
#pragma warning restore CA2025
        Assert.True(operation.IsCompleted);
        if (cancelBeforeCall)
        {
            Assert.True(operation.IsCanceled);
        }
        else
        {
            Assert.True(operation.IsCompletedSuccessfully);
        }

        return new WeakReference(cache);
    }

    private static TaskCompletionSource<bool> NewSignal() =>
        new(TaskCreationOptions.RunContinuationsAsynchronously);

    private static void UpdateMaximum(ref int maximum, int candidate)
    {
        int current;
        while (candidate > (current = Volatile.Read(ref maximum)) &&
               Interlocked.CompareExchange(ref maximum, candidate, current) != current)
        {
        }
    }
}
