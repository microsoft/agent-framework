// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the YAML frontmatter metadata parsed from a SKILL.md file.
/// </summary>
/// <remarks>
/// <para>
/// Frontmatter is the L1 (discovery) layer of the
/// <see href="https://agentskills.io/specification">Agent Skills specification</see>.
/// It contains the minimal metadata needed to advertise a skill in the system prompt
/// without loading the full skill content.
/// </para>
/// <para>
/// The constructor validates the name and description against specification rules
/// and throws <see cref="ArgumentException"/> if either value is invalid.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillFrontmatter
{
    /// <summary>
    /// Maximum allowed length for the skill name.
    /// </summary>
    internal const int MaxNameLength = 64;

    /// <summary>
    /// Maximum allowed length for the skill description.
    /// </summary>
    internal const int MaxDescriptionLength = 1024;

    /// <summary>
    /// Maximum allowed length for the compatibility field.
    /// </summary>
    internal const int MaxCompatibilityLength = 500;

    // Validates skill names per the Agent Skills specification (https://agentskills.io/specification#frontmatter):
    // lowercase letters, numbers, and hyphens only; must not start or end with a hyphen; must not contain consecutive hyphens.
    private static readonly Regex s_validNameRegex = new("^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$", RegexOptions.Compiled);

    private string? _compatibility;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillFrontmatter"/> class.
    /// </summary>
    /// <param name="name">Skill name in kebab-case.</param>
    /// <param name="description">Skill description for discovery.</param>
    /// <param name="compatibility">Optional compatibility information (max 500 chars).</param>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="name"/>, <paramref name="description"/>, or <paramref name="compatibility"/> violates the
    /// <see href="https://agentskills.io/specification">Agent Skills specification</see> rules.
    /// </exception>
    public AgentSkillFrontmatter(string name, string description, string? compatibility = null)
    {
        if (!ValidateName(name, out string? reason) ||
            !ValidateDescription(description, out reason) ||
            !ValidateCompatibility(compatibility, out reason))
        {
            throw new ArgumentException(reason);
        }

        this.Name = name;
        this.Description = description;
        this._compatibility = compatibility;
    }

    /// <summary>
    /// Gets the skill name. Lowercase letters, numbers, and hyphens only; no leading, trailing, or consecutive hyphens.
    /// </summary>
    public string Name { get; }

    /// <summary>
    /// Gets the skill description. Used for discovery in the system prompt.
    /// </summary>
    public string Description { get; }

    /// <summary>
    /// Gets or sets an optional license name or reference.
    /// </summary>
    public string? License { get; set; }

    /// <summary>
    /// Gets or sets optional compatibility information (max 500 chars).
    /// </summary>
    /// <exception cref="ArgumentException">
    /// Thrown when the value exceeds <see cref="MaxCompatibilityLength"/> characters.
    /// </exception>
    public string? Compatibility
    {
        get => this._compatibility;
        set
        {
            if (!ValidateCompatibility(value, out string? reason))
            {
                throw new ArgumentException(reason);
            }

            this._compatibility = value;
        }
    }

    /// <summary>
    /// Gets or sets optional space-delimited list of pre-approved tools.
    /// </summary>
    public string? AllowedTools { get; set; }

    /// <summary>
    /// Gets or sets the arbitrary key-value metadata for this skill.
    /// </summary>
    public AdditionalPropertiesDictionary? Metadata { get; set; }

    /// <summary>
    /// Validates a skill name against specification rules.
    /// </summary>
    /// <param name="name">The skill name to validate (may be <see langword="null"/>).</param>
    /// <param name="reason">When validation fails, contains a human-readable description of the failure.</param>
    /// <returns><see langword="true"/> if the name is valid; otherwise, <see langword="false"/>.</returns>
    public static bool ValidateName(
        string? name,
        [NotNullWhen(false)] out string? reason)
    {
        if (string.IsNullOrWhiteSpace(name))
        {
            reason = "Skill name is required.";
            return false;
        }

        if (name.Length > MaxNameLength)
        {
            reason = $"Skill name must be {MaxNameLength} characters or fewer.";
            return false;
        }

        if (!s_validNameRegex.IsMatch(name))
        {
            reason = "Skill name must use only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen or contain consecutive hyphens.";
            return false;
        }

        reason = null;
        return true;
    }

    /// <summary>
    /// Validates a skill description against specification rules.
    /// </summary>
    /// <param name="description">The skill description to validate (may be <see langword="null"/>).</param>
    /// <param name="reason">When validation fails, contains a human-readable description of the failure.</param>
    /// <returns><see langword="true"/> if the description is valid; otherwise, <see langword="false"/>.</returns>
    public static bool ValidateDescription(
        string? description,
        [NotNullWhen(false)] out string? reason)
    {
        if (string.IsNullOrWhiteSpace(description))
        {
            reason = "Skill description is required.";
            return false;
        }

        if (description.Length > MaxDescriptionLength)
        {
            reason = $"Skill description must be {MaxDescriptionLength} characters or fewer.";
            return false;
        }

        reason = null;
        return true;
    }

    /// <summary>
    /// Validates an optional skill compatibility value against specification rules.
    /// </summary>
    /// <param name="compatibility">The optional compatibility value to validate (may be <see langword="null"/>).</param>
    /// <param name="reason">When validation fails, contains a human-readable description of the failure.</param>
    /// <returns><see langword="true"/> if the value is valid; otherwise, <see langword="false"/>.</returns>
    public static bool ValidateCompatibility(
        string? compatibility,
        [NotNullWhen(false)] out string? reason)
    {
        if (compatibility?.Length > MaxCompatibilityLength)
        {
            reason = $"Skill compatibility must be {MaxCompatibilityLength} characters or fewer.";
            return false;
        }

        reason = null;
        return true;
    }
}
