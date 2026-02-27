// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parsed YAML frontmatter from a SKILL.md file, containing the skill's name and description.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkillFrontmatter
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillFrontmatter"/> class.
    /// </summary>
    /// <param name="name">Skill name.</param>
    /// <param name="description">Skill description.</param>
    internal FileAgentSkillFrontmatter(string name, string description)
    {
        this.Name = Throw.IfNullOrWhitespace(name);
        this.Description = Throw.IfNullOrWhitespace(description);
    }

    /// <summary>
    /// Gets the skill name. Lowercase letters, numbers, and hyphens only.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Gets the skill description. Used for discovery in the system prompt.
    /// </summary>
    public string Description { get; }
}
