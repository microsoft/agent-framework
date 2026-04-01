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
    public async Task GetSkillsAsync_PredicateIncludesAll_ReturnsAllSkills()
    {
        // Arrange
        var inner = new AgentInMemorySkillsSource(new AgentSkill[]
        {
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
            new AgentInlineSkill("skill-b", "B", "Instructions B."),
        });
        var source = new FilteringAgentSkillsSource(inner, _ => true);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
    }

    [Fact]
    public async Task GetSkillsAsync_PredicateExcludesAll_ReturnsEmpty()
    {
        // Arrange
        var inner = new AgentInMemorySkillsSource(new AgentSkill[]
        {
            new AgentInlineSkill("skill-a", "A", "Instructions A."),
            new AgentInlineSkill("skill-b", "B", "Instructions B."),
        });
        var source = new FilteringAgentSkillsSource(inner, _ => false);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    [Fact]
    public async Task GetSkillsAsync_PartialFilter_ReturnsMatchingSkillsOnly()
    {
        // Arrange
        var inner = new AgentInMemorySkillsSource(new AgentSkill[]
        {
            new AgentInlineSkill("keep-me", "Keep", "Instructions."),
            new AgentInlineSkill("drop-me", "Drop", "Instructions."),
            new AgentInlineSkill("keep-also", "KeepAlso", "Instructions."),
        });
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
    public async Task GetSkillsAsync_EmptySource_ReturnsEmpty()
    {
        // Arrange
        var inner = new AgentInMemorySkillsSource(Array.Empty<AgentSkill>());
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
        var inner = new AgentInMemorySkillsSource(Array.Empty<AgentSkill>());

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
    public async Task GetSkillsAsync_PreservesOrder()
    {
        // Arrange
        var inner = new AgentInMemorySkillsSource(new AgentSkill[]
        {
            new AgentInlineSkill("alpha", "Alpha", "Instructions."),
            new AgentInlineSkill("beta", "Beta", "Instructions."),
            new AgentInlineSkill("gamma", "Gamma", "Instructions."),
            new AgentInlineSkill("delta", "Delta", "Instructions."),
        });

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
