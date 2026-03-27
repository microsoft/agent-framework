// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text;
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
/// <see cref="AddResource(string, Delegate, string?)"/>, and <see cref="AddScript"/>
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
    private List<AgentSkillResource>? _resources;
    private List<AgentSkillScript>? _scripts;
    private string? _cachedContent;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentInlineSkill"/> class
    /// with a pre-built <see cref="AgentSkillFrontmatter"/>.
    /// </summary>
    /// <param name="frontmatter">The skill frontmatter containing name, description, and other metadata.</param>
    /// <param name="instructions">Skill instructions text.</param>
    public AgentInlineSkill(AgentSkillFrontmatter frontmatter, string instructions)
    {
        this.Frontmatter = Throw.IfNull(frontmatter);
        this._instructions = Throw.IfNullOrWhitespace(instructions);
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
    public AgentInlineSkill(
        string name,
        string description,
        string instructions,
        string? license = null,
        string? compatibility = null,
        string? allowedTools = null,
        AdditionalPropertiesDictionary? metadata = null)
        : this(
            new AgentSkillFrontmatter(name, description, compatibility)
            {
                License = license,
                AllowedTools = allowedTools,
                Metadata = metadata,
            },
            instructions)
    {
    }

    /// <inheritdoc/>
    public override AgentSkillFrontmatter Frontmatter { get; }

    /// <inheritdoc/>
    public override string Content => this._cachedContent ??= this.BuildContent();

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
    /// <returns>This instance, for chaining.</returns>
    public AgentInlineSkill AddResource(string name, Delegate method, string? description = null)
    {
        (this._resources ??= []).Add(new AgentInlineSkillResource(name, method, description));
        return this;
    }

    /// <summary>
    /// Registers a script with this skill, backed by a C# delegate.
    /// The delegate's parameters and return type are automatically marshaled via <c>AIFunctionFactory</c>.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">A method to execute when the script is invoked.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <returns>This instance, for chaining.</returns>
    public AgentInlineSkill AddScript(string name, Delegate method, string? description = null)
    {
        (this._scripts ??= []).Add(new AgentInlineSkillScript(name, method, description));
        return this;
    }

    private string BuildContent()
    {
        var sb = new StringBuilder();

        sb.Append($"<name>{EscapeXmlString(this.Frontmatter.Name)}</name>\n")
        .Append($"<description>{EscapeXmlString(this.Frontmatter.Description)}</description>\n\n")
        .Append("<instructions>\n")
        .Append(EscapeXmlString(this._instructions))
        .Append("\n</instructions>");

        if (this.Resources is { Count: > 0 })
        {
            sb.Append("\n\n<resources>\n");
            foreach (var resource in this.Resources)
            {
                if (resource.Description is not null)
                {
                    sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\" description=\"{EscapeXmlString(resource.Description)}\"/>\n");
                }
                else
                {
                    sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\"/>\n");
                }
            }

            sb.Append("</resources>");
        }

        if (this.Scripts is { Count: > 0 })
        {
            sb.Append("\n\n<scripts>\n");
            foreach (var script in this.Scripts)
            {
                JsonElement? parametersSchema = ((AgentInlineSkillScript)script).ParametersSchema;

                if (script.Description is null && parametersSchema is null)
                {
                    sb.Append($"  <script name=\"{EscapeXmlString(script.Name)}\"/>\n");
                }
                else
                {
                    sb.Append(script.Description is not null
                        ? $"  <script name=\"{EscapeXmlString(script.Name)}\" description=\"{EscapeXmlString(script.Description)}\">\n"
                        : $"  <script name=\"{EscapeXmlString(script.Name)}\">\n");

                    if (parametersSchema is not null)
                    {
                        sb.Append($"    <parameters_schema>{EscapeXmlString(parametersSchema.Value.GetRawText(), preserveQuotes: true)}</parameters_schema>\n");
                    }

                    sb.Append("  </script>\n");
                }
            }

            sb.Append("</scripts>");
        }

        return sb.ToString();
    }

    /// <summary>
    /// Escapes XML special characters: always escapes <c>&amp;</c>, <c>&lt;</c>, <c>&gt;</c>,
    /// <c>&quot;</c>, and <c>&apos;</c>. When <paramref name="preserveQuotes"/> is <see langword="true"/>,
    /// quotes are left unescaped to preserve readability of embedded content such as JSON.
    /// </summary>
    /// <param name="value">The string to escape.</param>
    /// <param name="preserveQuotes">
    /// When <see langword="true"/>, leaves <c>"</c> and <c>'</c> unescaped for use in XML element content (e.g., JSON).
    /// When <see langword="false"/> (default), escapes all XML special characters including quotes.
    /// </param>
    private static string EscapeXmlString(string value, bool preserveQuotes = false)
    {
        var result = value
            .Replace("&", "&amp;")
            .Replace("<", "&lt;")
            .Replace(">", "&gt;");

        if (!preserveQuotes)
        {
            result = result
                .Replace("\"", "&quot;")
                .Replace("'", "&apos;");
        }

        return result;
    }
}
