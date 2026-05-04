// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for all agent skills.
/// </summary>
/// <remarks>
/// <para>
/// A skill represents a domain-specific capability with instructions, resources, and scripts.
/// Concrete implementations include <see cref="AgentFileSkill"/> (filesystem-backed)
/// and <see cref="AgentInlineSkill"/> (code-defined).
/// </para>
/// <para>
/// Skill metadata follows the <see href="https://agentskills.io/specification">Agent Skills specification</see>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentSkill
{
    /// <summary>
    /// Gets the frontmatter metadata for this skill.
    /// </summary>
    /// <remarks>
    /// Contains the L1 discovery metadata (name, description, license, compatibility, etc.)
    /// as defined by the <see href="https://agentskills.io/specification">Agent Skills specification</see>.
    /// </remarks>
    public abstract AgentSkillFrontmatter Frontmatter { get; }

    /// <summary>
    /// Gets the full skill content.
    /// </summary>
    /// <remarks>
    /// For file-based skills this is the raw SKILL.md file content, optionally
    /// augmented with a synthesized scripts block when scripts are present.
    /// For code-defined skills this is a synthesized XML document
    /// containing name, description, and body (instructions, resources, scripts).
    /// </remarks>
    public abstract string Content { get; }

    /// <summary>
    /// Gets the resources associated with this skill, or <see langword="null"/> if none.
    /// </summary>
    /// <remarks>
    /// The default implementation returns <see langword="null"/>.
    /// Override this property in derived classes to provide skill-specific resources.
    /// </remarks>
    public virtual IReadOnlyList<AgentSkillResource>? Resources => null;

    /// <summary>
    /// Gets the scripts associated with this skill, or <see langword="null"/> if none.
    /// </summary>
    /// <remarks>
    /// The default implementation returns <see langword="null"/>.
    /// Override this property in derived classes to provide skill-specific scripts.
    /// </remarks>
    public virtual IReadOnlyList<AgentSkillScript>? Scripts => null;
}
