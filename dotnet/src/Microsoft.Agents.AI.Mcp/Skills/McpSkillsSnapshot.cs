// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill list and its listing-page lifetimes at a point in time.
/// </summary>
internal sealed class McpSkillsSnapshot
{
    /// <summary>
    /// Initializes a snapshot with its skills and listing-page lifetimes.
    /// </summary>
    /// <param name="skills">The complete skill list for this snapshot.</param>
    /// <param name="pageLifetimes">The receipt timestamp and TTL of each listing page.</param>
    public McpSkillsSnapshot(List<AgentSkill> skills, List<McpSkillsPageLifetime> pageLifetimes)
    {
        this.Skills = skills;
        this.PageLifetimes = pageLifetimes;
    }

    /// <summary>
    /// Gets the complete skill list for this snapshot.
    /// </summary>
    public List<AgentSkill> Skills { get; }

    /// <summary>
    /// Gets the receipt timestamp and TTL of each listing page.
    /// </summary>
    public List<McpSkillsPageLifetime> PageLifetimes { get; }
}
