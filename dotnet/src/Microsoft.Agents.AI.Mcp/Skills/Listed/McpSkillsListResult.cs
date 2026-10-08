// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// The result returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpSkillsListResult
{
    /// <summary>
    /// Gets the result type, which must be <c>complete</c>.
    /// </summary>
    public required string ResultType { get; init; }

    /// <summary>
    /// Gets the skills listed by the server.
    /// </summary>
    public required IReadOnlyList<McpListedSkillEntry?> Skills { get; init; }
}

/// <summary>
/// A skill entry returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpListedSkillEntry
{
    /// <summary>
    /// Gets the resource URI of the skill's <c>SKILL.md</c>.
    /// </summary>
    public required string Uri { get; init; }

    /// <summary>
    /// Gets the skill's name and description.
    /// </summary>
    public required McpListedSkillFrontmatter Frontmatter { get; init; }

    /// <summary>
    /// Gets the resources listed for the skill.
    /// </summary>
    public required IReadOnlyList<McpListedSkillResourceEntry> Resources { get; init; }
}

/// <summary>
/// The name and description of a skill returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpListedSkillFrontmatter
{
    /// <summary>
    /// Gets the skill's name.
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// Gets the skill's description.
    /// </summary>
    public required string Description { get; init; }
}

/// <summary>
/// A resource entry returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpListedSkillResourceEntry
{
    /// <summary>
    /// Gets the file's resource URI.
    /// </summary>
    public required string Uri { get; init; }
}
