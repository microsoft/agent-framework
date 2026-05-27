// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentSkillsProviderBuilder"/>.
/// </summary>
public sealed class AgentSkillsProviderBuilderTests
{
    private readonly TestAIAgent _agent = new();

    private AIContextProvider.InvokingContext CreateInvokingContext()
    {
        return new AIContextProvider.InvokingContext(this._agent, session: null, new AIContext());
    }

    [Fact]
    public void Build_NoSourceConfigured_Succeeds()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();

        // Act
        var provider = builder.Build();

        // Assert
        Assert.NotNull(provider);
    }

    [Fact]
    public void Build_WithCustomSource_Succeeds()
    {
        // Arrange
        var source = new TestAgentSkillsSource(
            new TestAgentSkill("custom", "Custom skill", "Instructions."));
        var builder = new AgentSkillsProviderBuilder()
            .UseSource(source);

        // Act
        var provider = builder.Build();

        // Assert
        Assert.NotNull(provider);
    }

    [Fact]
    public void UseSource_NullSource_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseSource(null!));
    }

    [Fact]
    public void UseFilter_NullPredicate_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseFilter(null!));
    }

    [Fact]
    public void UseFileScriptRunner_NullRunner_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseFileScriptRunner(null!));
    }

    [Fact]
    public void UseOptions_NullConfigure_ThrowsArgumentNullException()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseOptions(null!));
    }

    [Fact]
    public async Task Build_WithFilter_AppliesFilterToSkillsAsync()
    {
        // Arrange
        var source = new TestAgentSkillsSource(
            new TestAgentSkill("keep-me", "Keep", "Instructions."),
            new TestAgentSkill("drop-me", "Drop", "Instructions."));
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source)
            .UseFilter(skill => skill.Frontmatter.Name.StartsWith("keep", StringComparison.OrdinalIgnoreCase))
            .Build();

        // Act
        var result = await provider.InvokingAsync(
            this.CreateInvokingContext(), CancellationToken.None);

        // Assert — the instructions should mention "keep-me" but not "drop-me"
        Assert.NotNull(result.Instructions);
        Assert.Contains("keep-me", result.Instructions);
        Assert.DoesNotContain("drop-me", result.Instructions);
    }

    [Fact]
    public async Task Build_WithCacheDisabled_ReloadsOnEachCallAsync()
    {
        // Arrange
        var countingSource = new CountingSource(
            new TestAgentSkill("skill-a", "A", "Instructions."));
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(countingSource)
            .UseOptions(o => o.DisableCaching = true)
            .Build();

        // Act
        await provider.InvokingAsync(this.CreateInvokingContext(), CancellationToken.None);
        await provider.InvokingAsync(this.CreateInvokingContext(), CancellationToken.None);

        // Assert — inner source should be called each time (dedup still calls through)
        Assert.True(countingSource.CallCount >= 2);
    }

    [Fact]
    public async Task Build_WithCacheEnabled_CachesSkillsAsync()
    {
        // Arrange
        var countingSource = new CountingSource(
            new TestAgentSkill("skill-a", "A", "Instructions."));
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(countingSource)
            .Build();

        // Act
        await provider.InvokingAsync(this.CreateInvokingContext(), CancellationToken.None);
        await provider.InvokingAsync(this.CreateInvokingContext(), CancellationToken.None);

        // Assert — inner source should only be called once due to caching
        Assert.Equal(1, countingSource.CallCount);
    }

    [Fact]
    public void Build_FluentChaining_ReturnsSameBuilder()
    {
        // Arrange
        var builder = new AgentSkillsProviderBuilder();
        var source = new TestAgentSkillsSource(
            new TestAgentSkill("test", "Test", "Instructions."));

        // Act — all fluent methods should return the same builder
        var result = builder
            .UseSource(source)
            .UseScriptApproval(false)
            .UsePromptTemplate("Skills:\n{skills}\n{resource_instructions}\n{script_instructions}");

        // Assert
        Assert.Same(builder, result);
    }

    [Fact]
    public void Build_UseOptions_ConfiguresOptions()
    {
        // Arrange
        var source = new TestAgentSkillsSource(
            new TestAgentSkill("test", "Test", "Instructions."));

        // Act — UseOptions should not throw and successfully configure
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source)
            .UseOptions(opts => opts.ScriptApproval = true)
            .Build();

        // Assert
        Assert.NotNull(provider);
    }

    [Fact]
    public async Task Build_WithMultipleCustomSources_AggregatesAllAsync()
    {
        // Arrange
        var source1 = new TestAgentSkillsSource(
            new TestAgentSkill("from-one", "Source 1", "Instructions 1."));
        var source2 = new TestAgentSkillsSource(
            new TestAgentSkill("from-two", "Source 2", "Instructions 2."));
        var provider = new AgentSkillsProviderBuilder()
            .UseSource(source1)
            .UseSource(source2)
            .Build();

        // Act
        var result = await provider.InvokingAsync(
            this.CreateInvokingContext(), CancellationToken.None);

        // Assert
        Assert.NotNull(result.Instructions);
        Assert.Contains("from-one", result.Instructions);
        Assert.Contains("from-two", result.Instructions);
    }

    /// <summary>
    /// A test source that counts how many times GetSkillsAsync is called.
    /// </summary>
    private sealed class CountingSource : AgentSkillsSource
    {
        private readonly AgentSkill[] _skills;
        private int _callCount;

        public CountingSource(params AgentSkill[] skills)
        {
            this._skills = skills;
        }

        public int CallCount => this._callCount;

        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._callCount);
            return Task.FromResult<IList<AgentSkill>>(this._skills);
        }
    }
}
