// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides contextual information about a discovered file to the
/// <see cref="AgentFileSkillsSourceOptions.ScriptFilter"/> and
/// <see cref="AgentFileSkillsSourceOptions.ResourceFilter"/> predicates.
/// </summary>
public sealed class AgentFileSkillFilterContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillFilterContext"/> class.
    /// </summary>
    /// <param name="skillName">The name of the skill (from SKILL.md frontmatter).</param>
    /// <param name="relativeFilePath">
    /// The path to the script or resource file relative to the skill directory (using forward slashes).
    /// </param>
    internal AgentFileSkillFilterContext(string skillName, string relativeFilePath)
    {
        this.SkillName = Throw.IfNullOrWhitespace(skillName);
        this.RelativeFilePath = Throw.IfNullOrWhitespace(relativeFilePath);
    }

    /// <summary>
    /// Gets the name of the skill as declared in the SKILL.md frontmatter.
    /// </summary>
    /// <example><c>unit-converter</c></example>
    public string SkillName { get; }

    /// <summary>
    /// Gets the path to the script or resource file relative to the skill directory (using forward slashes).
    /// For root-level files this is just the filename; for nested files it includes the subdirectory.
    /// </summary>
    /// <example>
    /// <c>run.py</c> for a script at skill root,
    /// <c>scripts/convert.js</c> for a nested script, or
    /// <c>references/guide.md</c> for a nested resource.
    /// </example>
    public string RelativeFilePath { get; }
}
