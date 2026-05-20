// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkill"/> discovered from a filesystem directory backed by a SKILL.md file.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentFileSkill : AgentSkill
{
    private readonly IReadOnlyList<AgentSkillResource> _resources;
    private readonly IReadOnlyList<AgentSkillScript> _scripts;
    private readonly string _originalContent;
    private string? _content;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkill"/> class.
    /// </summary>
    /// <param name="frontmatter">The parsed frontmatter metadata for this skill.</param>
    /// <param name="content">The full raw SKILL.md file content including YAML frontmatter.</param>
    /// <param name="path">Absolute path to the directory containing this skill.</param>
    /// <param name="resources">Resources discovered for this skill.</param>
    /// <param name="scripts">Scripts discovered for this skill.</param>
    internal AgentFileSkill(
        AgentSkillFrontmatter frontmatter,
        string content,
        string path,
        IReadOnlyList<AgentSkillResource>? resources = null,
        IReadOnlyList<AgentSkillScript>? scripts = null)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._originalContent = Throw.IfNull(content);
        this.Path = Throw.IfNullOrWhitespace(path);
        this._resources = resources ?? [];
        this._scripts = scripts ?? [];
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Returns the raw SKILL.md content. When the skill has scripts, a
    /// <c>&lt;scripts&gt;&lt;script name="..."&gt;&lt;parameters_schema&gt;...&lt;/parameters_schema&gt;&lt;/script&gt;&lt;/scripts&gt;</c>
    /// block is appended with a per-script entry describing the expected argument format.
    /// The result is cached after the first access.
    /// </remarks>
    public override string Content
    {
        get => this._content ??= this._scripts is { Count: > 0 }
            ? this._originalContent + AgentInlineSkillContentBuilder.BuildScriptsBlock(this._scripts)
            : this._originalContent;
    }

    /// <summary>
    /// Gets the directory path where the skill was discovered.
    /// </summary>
    public string Path { get; }

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource> Resources => this._resources;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript> Scripts => this._scripts;
}
