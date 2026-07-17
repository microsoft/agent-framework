// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;

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
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>
    /// For file-based skills this is the raw SKILL.md file content, optionally
    /// augmented with a synthesized scripts block when scripts are present.
    /// For code-defined skills this is a synthesized XML document
    /// containing name, description, and body (instructions, resources, scripts).
    /// </returns>
    public abstract ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets a resource owned by this skill by name.
    /// </summary>
    /// <param name="name">The resource name (e.g. an identifier or a relative path referenced inside the skill content).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>
    /// The <see cref="AgentSkillResource"/>, or <see langword="null"/> when no resource with the given name exists.
    /// </returns>
    /// <remarks>
    /// The default implementation returns <see langword="null"/>. Override in derived classes that
    /// expose resources.
    /// </remarks>
    public virtual ValueTask<AgentSkillResource?> GetResourceAsync(
        string name,
        CancellationToken cancellationToken = default) => default;

    /// <summary>
    /// Gets a script owned by this skill by name.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>
    /// The <see cref="AgentSkillScript"/>, or <see langword="null"/> when no script with the given name exists.
    /// </returns>
    /// <remarks>
    /// The default implementation returns <see langword="null"/>. Override in derived classes that
    /// expose scripts.
    /// </remarks>
    public virtual ValueTask<AgentSkillScript?> GetScriptAsync(
        string name,
        CancellationToken cancellationToken = default) => default;
}
