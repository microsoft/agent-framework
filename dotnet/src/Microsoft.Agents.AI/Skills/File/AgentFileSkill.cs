// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkill"/> discovered from a filesystem directory backed by a SKILL.md file.
/// </summary>
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
    /// Returns the raw SKILL.md content with an <c>&lt;available_resources&gt;</c> and an
    /// <c>&lt;available_scripts&gt;</c> block appended, so the model gets an authoritative list for each
    /// category. A category with no entries is appended as a self-closing element (e.g.
    /// <c>&lt;available_scripts /&gt;</c>) so the model knows none are available and does not hallucinate
    /// their names. The result is cached after the first access.
    /// </remarks>
    public override ValueTask<string> GetContentAsync(CancellationToken cancellationToken = default)
    {
        this._content ??=
            this._originalContent
            + "\n" + AgentInlineSkillContentBuilder.BuildAvailableResourcesBlock(this._resources)
            + "\n" + AgentInlineSkillContentBuilder.BuildAvailableScriptsBlock(this._scripts);
        return new(this._content);
    }

    /// <summary>
    /// Gets the directory path where the skill was discovered.
    /// </summary>
    public string Path { get; }

    /// <inheritdoc/>
    public override ValueTask<AgentSkillResource?> GetResourceAsync(string name, CancellationToken cancellationToken = default)
    {
        var resource = this._resources.FirstOrDefault(r => r.Name == name);
        return new(resource);
    }

    /// <inheritdoc/>
    public override ValueTask<AgentSkillScript?> GetScriptAsync(string name, CancellationToken cancellationToken = default)
    {
        var script = this._scripts.FirstOrDefault(s => s.Name == name);
        return new(script);
    }
}
