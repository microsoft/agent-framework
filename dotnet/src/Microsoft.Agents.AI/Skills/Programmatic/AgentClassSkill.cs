// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for defining skills as C# classes that bundle all components together.
/// </summary>
/// <remarks>
/// <para>
/// Inherit from this class to create a self-contained skill definition. Override the abstract
/// properties to provide name, description, and instructions. Use <see cref="CreateResource(string, object, string?)"/>,
/// <see cref="CreateResource(string, Delegate, string?, JsonSerializerOptions?)"/>, and <see cref="CreateScript"/> to define
/// inline resources and scripts.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// public class PdfFormatterSkill : AgentClassSkill
/// {
///     private IReadOnlyList&lt;AgentSkillResource&gt;? _resources;
///     private IReadOnlyList&lt;AgentSkillScript&gt;? _scripts;
///
///     public override AgentSkillFrontmatter Frontmatter { get; } = new("pdf-formatter", "Format documents as PDF.");
///     protected override string Instructions =&gt; "Use this skill to format documents...";
///
///     public override IReadOnlyList&lt;AgentSkillResource&gt;? Resources =&gt; this._resources ??=
///     [
///         CreateResource("template", "Use this template..."),
///     ];
///
///     public override IReadOnlyList&lt;AgentSkillScript&gt;? Scripts =&gt; this._scripts ??=
///     [
///         CreateScript("format-pdf", FormatPdf),
///     ];
///
///     private static string FormatPdf(string content) =&gt; content;
/// }
/// </code>
/// </example>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentClassSkill : AgentSkill
{
    private string? _content;

    /// <summary>
    /// Gets the raw instructions text for this skill.
    /// </summary>
    protected abstract string Instructions { get; }

    /// <inheritdoc/>
    /// <remarks>
    /// Returns a synthesized XML document containing name, description, instructions, resources, and scripts.
    /// The result is cached after the first access. Override to provide custom content.
    /// </remarks>
    public override string Content => this._content ??= AgentInlineSkillContentBuilder.Build(
        this.Frontmatter.Name,
        this.Frontmatter.Description,
        this.Instructions,
        this.Resources,
        this.Scripts);

    /// <summary>
    /// Creates a skill resource backed by a static value.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="value">The static resource value.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <returns>A new <see cref="AgentSkillResource"/> instance.</returns>
    protected static AgentSkillResource CreateResource(string name, object value, string? description = null)
        => new AgentInlineSkillResource(name, value, description);

    /// <summary>
    /// Creates a skill resource backed by a delegate that produces a dynamic value.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="method">A method that produces the resource value when requested.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the delegate's parameters and return value.
    /// When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <returns>A new <see cref="AgentSkillResource"/> instance.</returns>
    protected static AgentSkillResource CreateResource(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
        => new AgentInlineSkillResource(name, method, description, serializerOptions);

    /// <summary>
    /// Creates a skill script backed by a delegate.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">A method to execute when the script is invoked.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the delegate's parameters and return value.
    /// When <see langword="null"/>, <see cref="AIJsonUtilities.DefaultOptions"/> is used.
    /// </param>
    /// <returns>A new <see cref="AgentSkillScript"/> instance.</returns>
    protected static AgentSkillScript CreateScript(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
        => new AgentInlineSkillScript(name, method, description, serializerOptions);
}
