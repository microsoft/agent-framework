// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AggregateAgentSkillsSource"/>.
/// </summary>
public sealed class AggregateAgentSkillsSourceTests
{
    [Fact]
    public async Task GetSkillsAsync_MultipleSources_AggregatesInRegistrationOrderAsyncAsync()
    {
        // Arrange
        var source1 = new TestAgentSkillsSource(
            new TestAgentSkill("alpha", "Alpha", "Instructions A."));
        var source2 = new TestAgentSkillsSource(
            new TestAgentSkill("beta", "Beta", "Instructions B."),
            new TestAgentSkill("gamma", "Gamma", "Instructions C."));
        var aggregate = new AggregateAgentSkillsSource([source1, source2]);

        // Act
        var result = await aggregate.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(3, result.Count);
        Assert.Equal("alpha", result[0].Frontmatter.Name);
        Assert.Equal("beta", result[1].Frontmatter.Name);
        Assert.Equal("gamma", result[2].Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_SingleSource_ReturnsItsSkillsAsyncAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("only", "Only skill", "Instructions."));
        var aggregate = new AggregateAgentSkillsSource([inner]);

        // Act
        var result = await aggregate.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(result);
        Assert.Equal("only", result[0].Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_AllSourcesEmpty_ReturnsEmptyListAsyncAsync()
    {
        // Arrange
        var source1 = new TestAgentSkillsSource(Array.Empty<AgentSkill>());
        var source2 = new TestAgentSkillsSource(Array.Empty<AgentSkill>());
        var aggregate = new AggregateAgentSkillsSource([source1, source2]);

        // Act
        var result = await aggregate.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task GetSkillsAsync_MixedEmptyAndNonEmptySources_ReturnsNonEmptySkillsAsyncAsync()
    {
        // Arrange
        var empty = new TestAgentSkillsSource(Array.Empty<AgentSkill>());
        var populated = new TestAgentSkillsSource(
            new TestAgentSkill("present", "Present", "Instructions."));
        var aggregate = new AggregateAgentSkillsSource([empty, populated, empty]);

        // Act
        var result = await aggregate.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(result);
        Assert.Equal("present", result[0].Frontmatter.Name);
    }

    [Fact]
    public async Task GetSkillsAsync_DoesNotDeduplicateAsyncAsync()
    {
        // Arrange
        var source1 = new TestAgentSkillsSource(
            new TestAgentSkill("shared", "From source 1", "Instructions 1."));
        var source2 = new TestAgentSkillsSource(
            new TestAgentSkill("shared", "From source 2", "Instructions 2."));
        var aggregate = new AggregateAgentSkillsSource([source1, source2]);

        // Act
        var result = await aggregate.GetSkillsAsync(CancellationToken.None);

        // Assert — duplicates are preserved (dedup is a separate decorator)
        Assert.Equal(2, result.Count);
        Assert.All(result, s => Assert.Equal("shared", s.Frontmatter.Name));
    }

    [Fact]
    public async Task GetSkillsAsync_CancellationTokenIsPropagatedAsyncAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var source = new CancellationAwareSource();
        var aggregate = new AggregateAgentSkillsSource([source]);

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => aggregate.GetSkillsAsync(cts.Token));
    }

    [Fact]
    public void Constructor_NullSources_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AggregateAgentSkillsSource(null!));
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
}
