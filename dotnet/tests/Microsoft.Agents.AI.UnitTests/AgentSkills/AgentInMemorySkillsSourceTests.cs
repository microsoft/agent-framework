// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="AgentInMemorySkillsSource"/>.
/// </summary>
public sealed class AgentInMemorySkillsSourceTests
{
    [Fact]
    public async Task GetSkillsAsync_ValidSkills_ReturnsAllAsync()
    {
        // Arrange
        var skills = new AgentSkill[]
        {
            new AgentInlineSkill("my-skill", "A valid skill.", "Instructions."),
            new AgentInlineSkill("another", "Another valid skill.", "More instructions."),
        };
        var source = new AgentInMemorySkillsSource(skills);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("my-skill", result[0].Frontmatter.Name);
        Assert.Equal("another", result[1].Frontmatter.Name);
    }

    [Theory]
    [InlineData("INVALID-NAME")]
    [InlineData("-leading")]
    [InlineData("trailing-")]
    public void Constructor_InvalidFrontmatter_ThrowsArgumentException(string invalidName)
    {
        // Act & Assert
        Assert.Throws<ArgumentException>(() =>
            new AgentInlineSkill(invalidName, "A skill.", "Instructions."));
    }

    [Fact]
    public void Constructor_NullSkills_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentInMemorySkillsSource(null!));
    }
}
