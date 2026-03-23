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
    public async Task GetSkillsAsync_ReturnsCachedResultAsync()
    {
        // Arrange
        var inner = new CountingSource(new TestAgentSkill("cached", "Cached skill", "Instructions."));
        var source = new CachingAgentSkillsSource(inner);

        // Act
        var result1 = await source.GetSkillsAsync(CancellationToken.None);
        var result2 = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(1, inner.CallCount);
        Assert.Same(result1, result2);
    }

    [Fact]
    public async Task GetSkillsAsync_ConcurrentCalls_LoadsOnlyOnceAsync()
    {
        // Arrange
        var inner = new CountingSource(new TestAgentSkill("concurrent", "Concurrent", "Instructions."));
        var source = new CachingAgentSkillsSource(inner);

        // Act
        var tasks = Enumerable.Range(0, 10)
            .Select(_ => source.GetSkillsAsync(CancellationToken.None))
            .ToArray();
        await Task.WhenAll(tasks);

        // Assert
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_EmptySource_CachesEmptyResultAsync()
    {
        // Arrange
        var inner = new CountingSource();
        var source = new CachingAgentSkillsSource(inner);

        // Act
        var result1 = await source.GetSkillsAsync(CancellationToken.None);
        _ = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result1);
        Assert.Equal(1, inner.CallCount);
    }

    [Fact]
    public async Task GetSkillsAsync_CancellationTokenForwardedToInnerSourceAsyncAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var inner = new CancellationAwareSource();
        var source = new CachingAgentSkillsSource(inner);

        // Act & Assert — the token should be forwarded to the inner source
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => source.GetSkillsAsync(cts.Token));
    }

    [Fact]
    public async Task GetSkillsAsync_SeparateInstances_CacheIndependentlyAsyncAsync()
    {
        // Arrange — use a source that returns a new list each time
        var callCount = 0;
        var freshSource = new DelegatingTestSource(() =>
        {
            Interlocked.Increment(ref callCount);
            return Task.FromResult<IList<AgentSkill>>(
                new List<AgentSkill> { new TestAgentSkill("shared", "Shared", "Instructions.") });
        });
        var source1 = new CachingAgentSkillsSource(freshSource);
        var source2 = new CachingAgentSkillsSource(freshSource);

        // Act
        var result1 = await source1.GetSkillsAsync(CancellationToken.None);
        var result2 = await source2.GetSkillsAsync(CancellationToken.None);

        // Assert — each instance caches independently, so inner is called twice
        Assert.Equal(2, callCount);
        Assert.NotSame(result1, result2);
    }

    /// <summary>
    /// A test source that counts calls.
    /// </summary>
    private sealed class CountingSource : AgentSkillsSource
    {
        private readonly IList<AgentSkill> _skills;
        private int _callCount;

        public CountingSource(params AgentSkill[] skills)
        {
            this._skills = skills;
        }

        public int CallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult(this._skills);
        }
    }

    /// <summary>
    /// A source that throws <see cref="OperationCanceledException"/> when the token is cancelled.
    /// </summary>
    private sealed class CancellationAwareSource : AgentSkillsSource
    {
        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult<IList<AgentSkill>>(new List<AgentSkill>());
        }
    }

    /// <summary>
    /// A source that delegates to a provided function, returning a fresh result each call.
    /// </summary>
    private sealed class DelegatingTestSource : AgentSkillsSource
    {
        private readonly Func<Task<IList<AgentSkill>>> _factory;

        public DelegatingTestSource(Func<Task<IList<AgentSkill>>> factory)
        {
            this._factory = factory;
        }

        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            return this._factory();
        }
    }
}
