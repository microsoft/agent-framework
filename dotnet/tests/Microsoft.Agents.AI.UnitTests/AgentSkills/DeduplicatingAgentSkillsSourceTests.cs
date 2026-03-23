// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Unit tests for <see cref="DeduplicatingAgentSkillsSource"/>.
/// </summary>
public sealed class DeduplicatingAgentSkillsSourceTests
{
    [Fact]
    public async Task GetSkillsAsync_NoDuplicates_ReturnsAllSkillsAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(
            new TestAgentSkill("skill-a", "A", "Instructions A."),
            new TestAgentSkill("skill-b", "B", "Instructions B."));
        var source = new DeduplicatingAgentSkillsSource(inner);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
    }

    [Fact]
    public async Task GetSkillsAsync_WithDuplicates_KeepsFirstOccurrenceAsync()
    {
        // Arrange
        var skills = new AgentSkill[]
        {
            new TestAgentSkill("dupe", "First", "Instructions 1."),
            new TestAgentSkill("dupe", "Second", "Instructions 2."),
            new TestAgentSkill("unique", "Unique", "Instructions 3."),
        };
        var inner = new TestAgentSkillsSource(skills);
        var source = new DeduplicatingAgentSkillsSource(inner);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Equal(2, result.Count);
        Assert.Equal("First", result.First(s => s.Frontmatter.Name == "dupe").Frontmatter.Description);
        Assert.Contains(result, s => s.Frontmatter.Name == "unique");
    }

    [Fact]
    public async Task GetSkillsAsync_CaseInsensitiveDuplication_KeepsFirstAsync()
    {
        // Arrange — use a custom source that returns skills with same name but different casing
        var inner = new FakeDuplicateCaseSource();
        var source = new DeduplicatingAgentSkillsSource(inner);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Single(result);
        Assert.Equal("First", result[0].Frontmatter.Description);
    }

    [Fact]
    public async Task GetSkillsAsync_EmptySource_ReturnsEmptyAsync()
    {
        // Arrange
        var inner = new TestAgentSkillsSource(System.Array.Empty<AgentSkill>());
        var source = new DeduplicatingAgentSkillsSource(inner);

        // Act
        var result = await source.GetSkillsAsync(CancellationToken.None);

        // Assert
        Assert.Empty(result);
    }

    /// <summary>
    /// A fake source that returns skills with names differing only by case.
    /// </summary>
    private sealed class FakeDuplicateCaseSource : AgentSkillsSource
    {
        public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
        {
            // AgentSkillFrontmatter validates names must be lowercase, so we build
            // two skills with the same lowercase name to test case-insensitive dedup.
            var skills = new List<AgentSkill>
            {
                new TestAgentSkill("my-skill", "First", "Instructions 1."),
                new TestAgentSkill("my-skill", "Second", "Instructions 2."),
            };
            return Task.FromResult<IList<AgentSkill>>(skills);
        }
    }
}
