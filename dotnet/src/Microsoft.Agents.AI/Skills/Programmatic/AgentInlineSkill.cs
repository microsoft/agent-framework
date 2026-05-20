// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A skill defined entirely in code with resources (static values or delegates) and scripts (delegates).
/// </summary>
/// <remarks>
/// All calls to <see cref="AddResource(string, object, string?)"/>,
/// <see cref="AddResource(string, Delegate, string?, JsonSerializerOptions?)"/>, and <see cref="AddScript"/>
/// must be made before the skill's <see cref="Content"/> is first accessed.
/// Calls made after that point will not be reflected in the generated
/// <see cref="Content"/>. In typical usage, this means configuring all
/// resources and scripts before registering the skill with an
/// <see cref="AgentSkillsProvider"/> or <see cref="AgentSkillsProviderBuilder"/>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentInlineSkill : AgentSkill
{
    private readonly string _instructions;
    private readonly JsonSerializerOptions? _serializerOptions;
    private List<AgentInlineSkillResource>? _resources;
    private List<AgentInlineSkillScript>? _scripts;
    private string? _cachedContent;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkill"/> class
    /// with a pre-built <see cref="AgentSkillFrontmatter"/>.
    /// </summary>
    /// <param name="frontmatter">The skill frontmatter containing name, description, and other metadata.</param>
    /// <param name="instructions">Skill instructions text.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> applied by default to all scripts and delegate resources
    /// added to this skill. Individual <see cref="AddScript"/> and <see cref="AddResource(string, Delegate, string?, JsonSerializerOptions?)"/>
    /// calls can override this default. When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    public AgentInlineSkill(AgentSkillFrontmatter frontmatter, string instructions, JsonSerializerOptions? serializerOptions = null)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._instructions = Throw.IfNullOrWhitespace(instructions);
        this._serializerOptions = serializerOptions;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkill"/> class
    /// with all frontmatter properties specified individually.
    /// </summary>
    /// <param name="name">Skill name in kebab-case.</param>
    /// <param name="description">Skill description for discovery.</param>
    /// <param name="instructions">Skill instructions text.</param>
    /// <param name="license">Optional license name or reference.</param>
    /// <param name="compatibility">Optional compatibility information (max 500 chars).</param>
    /// <param name="allowedTools">Optional space-delimited list of pre-approved tools.</param>
    /// <param name="metadata">Optional arbitrary key-value metadata.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> applied by default to all scripts and delegate resources
    /// added to this skill. Individual <see cref="AddScript"/> and <see cref="AddResource(string, Delegate, string?, JsonSerializerOptions?)"/>
    /// calls can override this default. When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    public AgentInlineSkill(
        string name,
        string description,
        string instructions,
        string? license = null,
        string? compatibility = null,
        string? allowedTools = null,
        AdditionalPropertiesDictionary? metadata = null,
        JsonSerializerOptions? serializerOptions = null)
        : this(
            new AgentSkillFrontmatter(name, description, compatibility)
            {
                License = license,
                AllowedTools = allowedTools,
                Metadata = metadata,
            },
            instructions,
            serializerOptions)
    {
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    public override string Content => this._cachedContent ??= AgentInlineSkillContentBuilder.Build(this.Frontmatter.Name, this.Frontmatter.Description, this._instructions, this._resources, this._scripts);

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillResource>? Resources => this._resources;

    /// <inheritdoc/>
    public override IReadOnlyList<AgentSkillScript>? Scripts => this._scripts;

    /// <summary>
    /// Registers a static resource with this skill.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="value">The static resource value.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <returns>This instance, for chaining.</returns>
    public AgentInlineSkill AddResource(string name, object value, string? description = null)
    {
        (this._resources ??= []).Add(new AgentInlineSkillResource(name, value, description));
        return this;
    }

    /// <summary>
    /// Registers a dynamic resource with this skill, backed by a C# delegate.
    /// The delegate's parameters and return type are automatically marshaled via <c>AIFunctionFactory</c>.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="method">A method that produces the resource value when requested.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> for this resource's delegate marshaling.
    /// When <see langword="null"/>, the skill-level default (if any) is used; otherwise <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <returns>This instance, for chaining.</returns>
    public AgentInlineSkill AddResource(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
    {
        (this._resources ??= []).Add(new AgentInlineSkillResource(name, method, description, serializerOptions ?? this._serializerOptions));
        return this;
    }

    /// <summary>
    /// Registers a script with this skill, backed by a C# delegate.
    /// The delegate's parameters and return type are automatically marshaled via <c>AIFunctionFactory</c>.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">A method to execute when the script is invoked.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> for this script's delegate marshaling.
    /// When <see langword="null"/>, the skill-level default (if any) is used; otherwise <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <returns>This instance, for chaining.</returns>
    public AgentInlineSkill AddScript(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
    {
        (this._scripts ??= []).Add(new AgentInlineSkillScript(name, method, description, serializerOptions ?? this._serializerOptions));
        return this;
    }
}
