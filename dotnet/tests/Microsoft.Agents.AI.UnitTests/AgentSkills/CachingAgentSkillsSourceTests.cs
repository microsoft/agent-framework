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
}
