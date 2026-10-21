// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Discovered and validated skills together with the lifetime of each discovery page.
/// </summary>
internal sealed class McpListedSkillsDiscoveryResult
{
    /// <summary>
    /// Initializes a discovery result with its skills and page lifetimes.
    /// </summary>
    /// <param name="skills">The complete list of discovered skills.</param>
    /// <param name="pageLifetimes">The receipt timestamp and TTL of each discovery page.</param>
    public McpListedSkillsDiscoveryResult(List<AgentSkill> skills, List<McpListedSkillsPageLifetime> pageLifetimes)
    {
        this.Skills = skills;
        this.PageLifetimes = pageLifetimes;
    }

    /// <summary>
    /// Gets the complete list of discovered skills.
    /// </summary>
    public List<AgentSkill> Skills { get; }

    /// <summary>
    /// Gets the receipt timestamp and TTL of each discovery page.
    /// </summary>
    public List<McpListedSkillsPageLifetime> PageLifetimes { get; }
}
