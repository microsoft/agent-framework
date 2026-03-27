// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="FilteringAgentSkillsSource"/>.
/// </summary>
public sealed class FilteringAgentSkillsSourceTests
{
    [Fact]
    public async Task GetSkillsAsync_PredicateIncludesAll_ReturnsAllSkillsAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("skill-a", "A", "Instructions A."),
            new TestAgentSkill("skill-b", "B", "Instructions B."));
        var source = new FilteringAgentSkillsSource(inner, _ => true);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
    }

    [Fact]
    public async Task GetSkillsAsync_PredicateExcludesAll_ReturnsEmptyAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("skill-a", "A", "Instructions A."),
            new TestAgentSkill("skill-b", "B", "Instructions B."));
        var source = new FilteringAgentSkillsSource(inner, _ => false);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task GetSkillsAsync_PartialFilter_ReturnsMatchingSkillsOnlyAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("keep-me", "Keep", "Instructions."),
            new TestAgentSkill("drop-me", "Drop", "Instructions."),
            new TestAgentSkill("keep-also", "KeepAlso", "Instructions."));
        var source = new FilteringAgentSkillsSource(
            inner,
            skill => skill.Frontmatter.Name.StartsWith("keep", StringComparison.OrdinalIgnoreCase));

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.All(result, s => Assert.StartsWith("keep", s.Frontmatter.Name));
    }

    [Fact]
    public async Task GetSkillsAsync_EmptySource_ReturnsEmptyAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(Array.Empty<AgentSkill>());
        var source = new FilteringAgentSkillsSource(inner, _ => true);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public void Constructor_NullPredicate_Throws()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(Array.Empty<AgentSkill>());

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FilteringAgentSkillsSource(inner, null!));
    }

    [Fact]
    public void Constructor_NullInnerSource_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FilteringAgentSkillsSource(null!, _ => true));
    }

    [Fact]
    public async Task GetSkillsAsync_PreservesOrderAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("alpha", "Alpha", "Instructions."),
            new TestAgentSkill("beta", "Beta", "Instructions."),
            new TestAgentSkill("gamma", "Gamma", "Instructions."),
            new TestAgentSkill("delta", "Delta", "Instructions."));

        // Keep only alpha and gamma
        var source = new FilteringAgentSkillsSource(
            inner,
            skill => skill.Frontmatter.Name is "alpha" or "gamma");

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("alpha", result[0].Frontmatter.Name);
        Assert.Equal("gamma", result[1].Frontmatter.Name);
    }
}
