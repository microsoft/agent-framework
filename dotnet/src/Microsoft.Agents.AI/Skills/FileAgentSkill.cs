// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a loaded Agent Skill discovered from a filesystem directory.
/// </summary>
/// <remarks>
/// Each skill is backed by a <c>SKILL.md</c> file containing YAML frontmatter (name and description)
/// and a markdown body with instructions. Resource files referenced in the body are validated at
/// discovery time and read from disk on demand.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkill
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkill"/> class.
    /// </summary>
    /// <param name="frontmatter">Parsed YAML frontmatter (name and description).</param>
    /// <param name="body">The SKILL.md content after the closing <c>---</c> delimiter.</param>
    /// <param name="sourcePath">Absolute path to the directory containing this skill.</param>
    /// <param name="resourceNames">Relative paths of resource files referenced in the skill body.</param>
    internal FileAgentSkill(
        FileAgentSkillFrontmatter frontmatter,
        string body,
        string sourcePath,
        IReadOnlyList<string>? resourceNames = null)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this.Body = Throw.IfNull(body);
        this.SourcePath = Throw.IfNullOrWhitespace(sourcePath);
        this.ResourceNames = resourceNames ?? [];
    }

    /// <summary>
    /// Gets the parsed YAML frontmatter (name and description).
    /// </summary>
    public FileAgentSkillFrontmatter Frontmatter { get; }

    /// <summary>
    /// Gets the directory path where the skill was discovered.
    /// </summary>
    public string SourcePath { get; }

    /// <summary>
    /// Gets the SKILL.md body content (without the YAML frontmatter).
    /// </summary>
    internal string Body { get; }

    /// <summary>
    /// Gets the relative paths of resource files referenced in the skill body (e.g., "references/FAQ.md").
    /// </summary>
    internal IReadOnlyList<string> ResourceNames { get; }
}
