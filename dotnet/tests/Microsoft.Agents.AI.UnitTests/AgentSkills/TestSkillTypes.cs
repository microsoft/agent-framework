// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// A simple in-memory <see cref="AgentSkill"/> implementation for unit tests.
/// </summary>
internal sealed class TestAgentSkill : AgentSkill
{
    private readonly AgentSkillFrontmatter _frontmatter;
    private readonly string _content;

    /// <summary>
    /// Initializes a new instance of the <see cref="TestAgentSkill"/> class.
    /// </summary>
    /// <param name="name">Kebab-case skill name.</param>
    /// <param name="description">Skill description.</param>
    /// <param name="content">Full skill content (body text).</param>
    public TestAgentSkill(string name, string description, string content)
    {
        this._frontmatter = new AgentSkillFrontmatter(name, description);
        this._content = content;
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter => this._frontmatter;

    /// <inheritdoc/>
    public override string Content => this._content;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources => null;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => null;
}

/// <summary>
/// A simple in-memory <see cref="AgentSkillsSource"/> implementation for unit tests.
/// </summary>
internal sealed class TestAgentSkillsSource : AgentSkillsSource
{
    private readonly IList<AgentSkill> _skills;

    /// <summary>
    /// Initializes a new instance of the <see cref="TestAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="skills">The skills to return.</param>
    public TestAgentSkillsSource(IList<AgentSkill> skills)
    {
        this._skills = skills;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="TestAgentSkillsSource"/> class.
    /// </summary>
    /// <param name="skills">The skills to return.</param>
    public TestAgentSkillsSource(params AgentSkill[] skills)
    {
        this._skills = skills;
    }

    /// <inheritdoc/>
    public override Task<IList<AgentSkill>> GetSkillsAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult(this._skills);
    }
}
