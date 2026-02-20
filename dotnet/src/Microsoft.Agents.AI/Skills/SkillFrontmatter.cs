// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Parsed YAML frontmatter from a SKILL.md file, containing the skill's name and description.
/// </summary>
internal sealed class SkillFrontmatter
{
    /// <summary>
    /// Initializes a new instance of the <see cref="SkillFrontmatter"/> class.
    /// </summary>
    /// <param name="name">Skill name (lowercase, hyphens, max 64 characters).</param>
    /// <param name="description">Skill description (max 1024 characters).</param>
    public SkillFrontmatter(string name, string description)
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
