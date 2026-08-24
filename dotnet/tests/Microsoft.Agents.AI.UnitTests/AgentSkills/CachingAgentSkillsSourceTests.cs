// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="CachingAgentSkillsSource"/>.
/// </summary>
public sealed class CachingAgentSkillsSourceTests
{
    [Fact]
    public async Task GetSkillsAsync_MultipleInvocations_CallsInnerSourceOnceAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var result1 = await source.GetSkillsAsync(context, CancellationToken.None);
        var result2 = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.Same(result1, result2);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_ConcurrentInvocations_CallsInnerSourceOnceAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-b", "B", "Instructions B."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var tasks = Enumerable.Range(0, 10)
            .Select(_ => source.GetSkillsAsync(context, CancellationToken.None))
            .ToArray();
        var results = await Task.WhenAll(tasks);

        // Assert
        Assert.Equal(1, inner.CallCount);
        foreach (var result in results)
        {
            Assert.Same(results[0], result);
        }
    }

    [Fact]
    public async Task GetSkillsAsync_InnerSourceThrows_DoesNotCacheErrorAsync()
    {
        // Arrange
        var inner = new FailingSkillsSource(failOnFirstCall: true);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act — first call fails
        await Assert.ThrowsAsync<InvalidOperationException>(() => source.GetSkillsAsync(context, CancellationToken.None));

        // Act — second call succeeds (cache was cleared)
        var result = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.Single(result);
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_ReturnsResultFromInnerSourceAsync()
    {
        // Arrange
        var skills = new AgentSkill[]
        {
            new AgentInlineSkill("skill-x", "X", "Body X."),
            new AgentInlineSkill("skill-y", "Y", "Body Y."),
        };
        var inner = new CountingSkillsSource(skills);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var result = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("skill-x", result[0].Frontmatter.Name);
        Assert.Equal("skill-y", result[1].Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SameIsolationKey_CallsInnerSourceOnceAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { CacheIsolationKeySelector = _ => "same-key" });
        var context1 = TestAgentSkillsSourceContextFactory.Create();
        var context2 = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var result1 = await source.GetSkillsAsync(context1, CancellationToken.None);
        var result2 = await source.GetSkillsAsync(context2, CancellationToken.None);

        // Assert
        Assert.Same(result1, result2);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_DifferentIsolationKeys_CachesSeparatelyAsync()
    {
        // Arrange
        var agent1 = new TestAIAgent();
        var agent2 = new TestAIAgent();
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions
            {
                CacheIsolationKeySelector = context => ReferenceEquals(context.Agent, agent1) ? "agent-1" : "agent-2",
            });
        var context1 = TestAgentSkillsSourceContextFactory.Create(agent1);
        var context2 = TestAgentSkillsSourceContextFactory.Create(agent2);

        // Act
        await source.GetSkillsAsync(context1, CancellationToken.None);
        await source.GetSkillsAsync(context2, CancellationToken.None);

        // Assert
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_NullIsolationKey_UsesSharedCacheAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { CacheIsolationKeySelector = _ => null });
        var context1 = TestAgentSkillsSourceContextFactory.Create();
        var context2 = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var result1 = await source.GetSkillsAsync(context1, CancellationToken.None);
        var result2 = await source.GetSkillsAsync(context2, CancellationToken.None);

        // Assert
        Assert.Same(result1, result2);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_EmptyStringIsolationKey_IsolatedFromSharedCacheAsync()
    {
        // Arrange
        string? isolationKey = null;
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { CacheIsolationKeySelector = _ => isolationKey });
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        await source.GetSkillsAsync(context, CancellationToken.None); // shared bucket
        isolationKey = string.Empty;
        await source.GetSkillsAsync(context, CancellationToken.None); // distinct empty-string bucket

        // Assert
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_FirstCallerCancels_OtherCallerStillGetsResultAsync()
    {
        // Arrange
        var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var inner = new DelayedSkillsSource(gate.Task,
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        using var cts1 = new CancellationTokenSource();
        using var cts2 = new CancellationTokenSource();

        // Act — start the first caller and wait until it owns the gate and its fetch has started,
        // so the second caller is guaranteed to queue behind it (and not become the fetch owner).
        var task1 = source.GetSkillsAsync(context, cts1.Token);
        await inner.Started;

        // The second caller now queues behind the first on the cache gate.
        var task2 = source.GetSkillsAsync(context, cts2.Token);

        // Cancel the first caller; its fetch is cancelled and the gate is released.
        cts1.Cancel();
        await Assert.ThrowsAsync<OperationCanceledException>(() => task1);

        // The second caller acquires the gate and starts a fresh fetch; release the inner source.
        gate.SetResult(true);
        var result = await task2;

        // Assert — the second caller performs its own fetch (restart semantics).
        Assert.Single(result);
        Assert.Equal("skill-a", result[0].Frontmatter.Name);
        Assert.Equal(2, inner.CallCount);
        Assert.False(inner.LastCancellationToken.IsCancellationRequested);
    }

    [Fact]
    public async Task GetSkillsAsync_AllCallersCancel_InnerSourceIsCancelledAsync()
    {
        // Arrange
        var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var inner = new DelayedSkillsSource(gate.Task,
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        using var cts1 = new CancellationTokenSource();
        using var cts2 = new CancellationTokenSource();

        // Act
        var task1 = source.GetSkillsAsync(context, cts1.Token);
        var task2 = source.GetSkillsAsync(context, cts2.Token);

        // Wait until the first caller's fetch has started; the second caller is queued on the gate.
        await inner.Started;

        // Cancel both callers
        cts1.Cancel();
        cts2.Cancel();

        await Assert.ThrowsAsync<OperationCanceledException>(() => task1);
        await Assert.ThrowsAsync<OperationCanceledException>(() => task2);

        // Assert — the inner source's cancellation token should have been triggered
        Assert.True(inner.LastCancellationToken.IsCancellationRequested);
    }

    [Fact]
    public async Task GetSkillsAsync_SingleCallerCancels_InnerSourceIsCancelledAsync()
    {
        // Arrange
        var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var inner = new DelayedSkillsSource(gate.Task,
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        using var cts = new CancellationTokenSource();

        // Act
        var task = source.GetSkillsAsync(context, cts.Token);

        // Give task time to start
        await inner.Started;

        // Cancel the only caller
        cts.Cancel();
        await Assert.ThrowsAsync<OperationCanceledException>(() => task);

        // Assert — the inner source's cancellation token should have been triggered
        Assert.True(inner.LastCancellationToken.IsCancellationRequested);
    }

    [Fact]
    public async Task GetSkillsAsync_CancelledCaller_DoesNotPoisonSubsequentCallAsync()
    {
        // Arrange
        var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var inner = new DelayedSkillsSource(gate.Task,
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        using var cts = new CancellationTokenSource();

        // Act — first caller cancels while alone, cancelling the inner fetch.
        var task = source.GetSkillsAsync(context, cts.Token);
        await inner.Started;
        cts.Cancel();
        await Assert.ThrowsAsync<OperationCanceledException>(() => task);

        // A fresh caller should trigger a new fetch and succeed.
        gate.SetResult(true);
        var result = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.Single(result);
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_WithinRefreshInterval_ReturnsCachedResultAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { RefreshInterval = TimeSpan.FromHours(1) });
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act — both calls fall well within the refresh interval.
        var result1 = await source.GetSkillsAsync(context, CancellationToken.None);
        var result2 = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert — the cached result is reused while fresh.
        Assert.Same(result1, result2);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_ZeroRefreshInterval_AlwaysRefetchesAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { RefreshInterval = TimeSpan.Zero });
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        await source.GetSkillsAsync(context, CancellationToken.None);
        await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert — a zero interval treats the cached result as always stale.
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_NegativeRefreshInterval_AlwaysRefetchesAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { RefreshInterval = TimeSpan.FromMinutes(-1) });
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        await source.GetSkillsAsync(context, CancellationToken.None);
        await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert — a negative interval treats the cached result as always stale.
        Assert.Equal(2, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_NullRefreshInterval_ReturnsCachedResultAsync()
    {
        // Arrange
        var inner = new CountingSkillsSource(
        [
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
        ]);
        var source = new CachingAgentSkillsSource(
            inner,
            new CachingAgentSkillsSourceOptions { RefreshInterval = null });
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Act
        var result1 = await source.GetSkillsAsync(context, CancellationToken.None);
        var result2 = await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert — with no interval the cached result never expires.
        Assert.Same(result1, result2);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public void Dispose_DisposesInnerSource()
    {
        // Arrange
        var inner = new DisposeTrackingSkillsSource();
        var source = new CachingAgentSkillsSource(inner);

        // Act
        source.Dispose();

        // Assert — disposal cascades to the wrapped source.
        Assert.Equal(1, inner.DisposeCount);
    }

    [Fact]
    public async Task Dispose_IsIdempotentAsync()
    {
        // Arrange
        var inner = new DisposeTrackingSkillsSource();
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();

        // Populate a cache entry so a semaphore exists to dispose.
        await source.GetSkillsAsync(context, CancellationToken.None);

        // Act
        source.Dispose();
        source.Dispose();

        // Assert — the inner source is disposed exactly once.
        Assert.Equal(1, inner.DisposeCount);
    }

    [Fact]
    public async Task GetSkillsAsync_AfterDispose_ThrowsObjectDisposedExceptionAsync()
    {
        // Arrange
        var inner = new DisposeTrackingSkillsSource();
        var source = new CachingAgentSkillsSource(inner);
        var context = TestAgentSkillsSourceContextFactory.Create();
        source.Dispose();

        // Act & Assert — calls after disposal fail deterministically and create no cache entries.
        await Assert.ThrowsAsync<ObjectDisposedException>(() => source.GetSkillsAsync(context, CancellationToken.None));
    }

    private sealed class DisposeTrackingSkillsSource : AgentSkillsSource
    {
        public int DisposeCount { get; private set; }

        public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
            => Task.FromResult<IList<AgentSkill>>([]);

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this.DisposeCount++;
            }

            base.Dispose(disposing);
        }
    }

    private sealed class CountingSkillsSource : AgentSkillsSource
    {
        private readonly IList<AgentSkill> _skills;
        private int _callCount;

        public CountingSkillsSource(IList<AgentSkill> skills)
        {
            this._skills = skills;
        }

        public int CallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult(this._skills);
        }
    }

    private sealed class FailingSkillsSource : AgentSkillsSource
    {
        private readonly bool _failOnFirstCall;
        private int _callCount;

        public FailingSkillsSource(bool failOnFirstCall)
        {
            this._failOnFirstCall = failOnFirstCall;
        }

        public int CallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        {
            var count = Interlocked.Increment(ref this._callCount);
            if (this._failOnFirstCall && count == 1)
            {
                throw new InvalidOperationException("Simulated failure.");
            }

            return Task.FromResult<IList<AgentSkill>>(new List<AgentSkill>
            {
                new AgentInlineSkill("recovered-skill", "Recovered", "Body."),
            });
        }
    }

    private sealed class DelayedSkillsSource : AgentSkillsSource
    {
        private readonly Task _gate;
        private readonly IList<AgentSkill> _skills;
        private readonly TaskCompletionSource<bool> _started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _callCount;

        public DelayedSkillsSource(Task gate, IList<AgentSkill> skills)
        {
            this._gate = gate;
            this._skills = skills;
        }

        public int CallCount => this._callCount;

        public CancellationToken LastCancellationToken { get; private set; }

        /// <summary>Completes once the inner source has started executing at least once.</summary>
        public Task Started => this._started.Task;

        public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            this.LastCancellationToken = cancellationToken;
            this._started.TrySetResult(true);

            // Wait for the gate to open or for cancellation, whichever comes first.
            var cancellationTcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            using (cancellationToken.Register(static state => ((TaskCompletionSource<bool>)state!).TrySetResult(true), cancellationTcs))
            {
                if (this._gate == await Task.WhenAny(this._gate, cancellationTcs.Task).ConfigureAwait(false))
                {
                    return this._skills;
                }
            }

            cancellationToken.ThrowIfCancellationRequested();
            return this._skills; // Unreachable
        }
    }
}
