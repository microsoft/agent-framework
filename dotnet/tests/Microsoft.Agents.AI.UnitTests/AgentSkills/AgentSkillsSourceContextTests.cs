// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillsSourceContext"/> and its integration with
/// <see cref="AgentSkillsSource.GetSkillsAsync"/> and <see cref="AgentSkillsProvider"/>.
/// </summary>
public sealed class AgentSkillsSourceContextTests
{
    private readonly TestAIAgent _agent = new();

    [Fact]
    public void Constructor_NullAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentSkillsSourceContext(null!));
    }

    [Fact]
    public void Constructor_ValidAgent_SetsAgentProperty()
    {
        // Arrange & Act
        var context = new AgentSkillsSourceContext(this._agent);

        // Assert
        Assert.Same(this._agent, context.Agent);
    }

    [Fact]
    public async Task GetSkillsAsync_ReceivesContextWithCorrectAgentAsync()
    {
        // Arrange
        var capturingSource = new ContextCapturingSkillsSource(
            new AgentInlineSkill("test-skill", "Test skill.", "Instructions."));
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await capturingSource.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(capturingSource.CapturedContext);
        Assert.Same(this._agent, capturingSource.CapturedContext!.Agent);
    }

    [Fact]
    public async Task AgentSkillsProvider_PassesAgentContextToSourceAsync()
    {
        // Arrange
        var capturingSource = new ContextCapturingSkillsSource(
            new AgentInlineSkill("provider-skill", "Provider skill.", "Instructions."));
        var provider = new AgentSkillsProvider(capturingSource, options: new AgentSkillsProviderOptions { DisableCaching = true });
        var invokingContext = new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());

        // Act
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — the provider should have created a context with the invoking agent
        Assert.NotNull(capturingSource.CapturedContext);
        Assert.Same(this._agent, capturingSource.CapturedContext!.Agent);
    }

    [Fact]
    public async Task AgentSkillsProvider_DifferentAgents_PassesDifferentContextsAsync()
    {
        // Arrange
        var agentA = new TestAIAgent();
        var agentB = new TestAIAgent();
        var capturingSource = new ContextCapturingSkillsSource(
            new AgentInlineSkill("multi-agent-skill", "Skill.", "Instructions."));
        var provider = new AgentSkillsProvider(capturingSource, options: new AgentSkillsProviderOptions { DisableCaching = true });

        var contextA = new AIContextProvider.InvokingContext(agentA, session: null, new AIContext());
        var contextB = new AIContextProvider.InvokingContext(agentB, session: null, new AIContext());

        // Act — invoke for agent A
        await provider.InvokingAsync(contextA, CancellationToken.None);
        var capturedAgentA = capturingSource.CapturedContext?.Agent;

        // Act — invoke for agent B
        await provider.InvokingAsync(contextB, CancellationToken.None);
        var capturedAgentB = capturingSource.CapturedContext?.Agent;

        // Assert
        Assert.Same(agentA, capturedAgentA);
        Assert.Same(agentB, capturedAgentB);
        Assert.NotSame(capturedAgentA, capturedAgentB);
    }

    [Fact]
    public async Task AgentSkillsProvider_SameAgent_CachesSkillsAsync()
    {
        // Arrange
        var agent = new TestAIAgent();
        var countingSource = new CallCountingSkillsSource(
            new AgentInlineSkill("cached-skill", "Cached.", "Instructions."));
        var provider = new AgentSkillsProvider(countingSource);

        var invokingContext = new AIContextProvider.InvokingContext(agent, session: null, new AIContext());

        // Act — two invocations with the same agent
        await provider.InvokingAsync(invokingContext, CancellationToken.None);
        await provider.InvokingAsync(invokingContext, CancellationToken.None);

        // Assert — cached after first call, so source called only once
        Assert.Equal(1, countingSource.CallCount);
    }

    [Fact]
    public async Task AgentSkillsProvider_DifferentAgents_CallsSourceForEachAsync()
    {
        // Arrange
        var agentA = new TestAIAgent();
        var agentB = new TestAIAgent();
        var countingSource = new CallCountingSkillsSource(
            new AgentInlineSkill("per-agent-skill", "Per-agent.", "Instructions."));
        var provider = new AgentSkillsProvider(countingSource);

        var contextA = new AIContextProvider.InvokingContext(agentA, session: null, new AIContext());
        var contextB = new AIContextProvider.InvokingContext(agentB, session: null, new AIContext());

        // Act — two invocations for agent A (cached), one for agent B (new cache entry)
        await provider.InvokingAsync(contextA, CancellationToken.None);
        await provider.InvokingAsync(contextA, CancellationToken.None);
        await provider.InvokingAsync(contextB, CancellationToken.None);

        // Assert — source called once per distinct agent
        Assert.Equal(2, countingSource.CallCount);
    }

    [Fact]
    public async Task DelegatingSource_PropagatesContextToInnerSourceAsync()
    {
        // Arrange
        var inner = new ContextCapturingSkillsSource(
            new AgentInlineSkill("delegated-skill", "Delegated skill.", "Instructions."));
        var outer = new PassThroughDelegatingSource(inner);
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await outer.GetSkillsAsync(context, CancellationToken.None);

        // Assert — the inner source should have received the same context
        Assert.NotNull(inner.CapturedContext);
        Assert.Same(context, inner.CapturedContext);
    }

    [Fact]
    public async Task FilteringSource_PropagatesContextToInnerSourceAsync()
    {
        // Arrange
        var inner = new ContextCapturingSkillsSource(
            new AgentInlineSkill("filter-skill", "Skill to filter.", "Instructions."));
        var filtering = new FilteringAgentSkillsSource(inner, _ => true);
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await filtering.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(inner.CapturedContext);
        Assert.Same(context, inner.CapturedContext);
    }

    [Fact]
    public async Task DeduplicatingSource_PropagatesContextToInnerSourceAsync()
    {
        // Arrange
        var inner = new ContextCapturingSkillsSource(
            new AgentInlineSkill("dedup-skill", "Dedup skill.", "Instructions."));
        var deduplicating = new DeduplicatingAgentSkillsSource(inner);
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await deduplicating.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.NotNull(inner.CapturedContext);
        Assert.Same(context, inner.CapturedContext);
    }

    [Fact]
    public async Task AggregatingSource_PropagatesContextToAllChildSourcesAsync()
    {
        // Arrange
        var innerA = new ContextCapturingSkillsSource(
            new AgentInlineSkill("skill-a", "Skill A.", "Instructions."));
        var innerB = new ContextCapturingSkillsSource(
            new AgentInlineSkill("skill-b", "Skill B.", "Instructions."));
        var aggregating = new AggregatingAgentSkillsSource([innerA, innerB]);
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await aggregating.GetSkillsAsync(context, CancellationToken.None);

        // Assert — both child sources receive the same context
        Assert.NotNull(innerA.CapturedContext);
        Assert.Same(context, innerA.CapturedContext);
        Assert.NotNull(innerB.CapturedContext);
        Assert.Same(context, innerB.CapturedContext);
    }

    [Fact]
    public async Task TestAgentSkillsSource_CapturesContextAsync()
    {
        // Arrange
        var source = new TestAgentSkillsSource(
            new AgentInlineSkill("ts-skill", "Test source skill.", "Instructions."));
        var context = new AgentSkillsSourceContext(this._agent);

        // Act
        await source.GetSkillsAsync(context, CancellationToken.None);

        // Assert
        Assert.Same(context, source.LastContext);
    }

    /// <summary>
    /// A skill source that counts how many times <see cref="GetSkillsAsync"/> is called.
    /// </summary>
    private sealed class CallCountingSkillsSource : AgentSkillsSource
    {
        private readonly List<AgentSkill> _skills;
        private int _callCount;

        public CallCountingSkillsSource(params AgentSkill[] skills)
        {
            this._skills = [.. skills];
        }

        public int CallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult<IList<AgentSkill>>(this._skills);
        }
    }

    /// <summary>
    /// A skill source that captures the context passed to <see cref="GetSkillsAsync"/>.
    /// </summary>
    private sealed class ContextCapturingSkillsSource : AgentSkillsSource
    {
        private readonly List<AgentSkill> _skills;

        public ContextCapturingSkillsSource(params AgentSkill[] skills)
        {
            this._skills = [.. skills];
        }

        public AgentSkillsSourceContext? CapturedContext { get; private set; }

        public override Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
        {
            this.CapturedContext = context;
            return Task.FromResult<IList<AgentSkill>>(this._skills);
        }
    }

    /// <summary>
    /// A minimal delegating source that passes through to the inner source unchanged.
    /// Used to verify context propagation through the decorator chain.
    /// </summary>
    private sealed class PassThroughDelegatingSource : DelegatingAgentSkillsSource
    {
        public PassThroughDelegatingSource(AgentSkillsSource innerSource)
            : base(innerSource)
        {
        }
    }
}
