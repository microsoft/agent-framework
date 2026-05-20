// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Abstract base class for defining skills as C# classes that bundle all components together.
/// </summary>
/// <typeparam name="TSelf">
/// The concrete skill type. This type parameter is annotated with
/// <see cref="DynamicallyAccessedMembersAttribute"/> to ensure that the IL trimmer and Native AOT compiler
/// preserve the members needed for attribute-based discovery.
/// </typeparam>
/// <remarks>
/// <para>
/// Inherit from this class to create a self-contained skill definition. Override the abstract
/// properties to provide name, description, and instructions.
/// </para>
/// <para>
/// Scripts and resources can be defined in two ways:
/// <list type="bullet">
/// <item>
/// <b>Attribute-based (recommended):</b> Annotate methods with <see cref="AgentSkillScriptAttribute"/> to define scripts,
/// and properties or methods with <see cref="AgentSkillResourceAttribute"/> to define resources. These are automatically
/// discovered via reflection on <typeparamref name="TSelf"/>. This approach is compatible with Native AOT.
/// </item>
/// <item>
/// <b>Explicit override:</b> Override <see cref="AgentSkill.Resources"/> and <see cref="AgentSkill.Scripts"/>, using
/// <see cref="CreateResource(string, object, string?)"/>, <see cref="CreateResource(string, Delegate, string?, JsonSerializerOptions?)"/>,
/// and <see cref="CreateScript"/> to define inline resources and scripts. This approach is also compatible with Native AOT.
/// </item>
/// </list>
/// </para>
/// <para>
/// <b>Multi-level inheritance limitation:</b> Discovery reflects only on <typeparamref name="TSelf"/>,
/// so if a further-derived subclass adds new attributed members, they will not be discovered unless
/// that subclass also uses the CRTP pattern
/// (e.g., <c>class SpecialSkill : AgentClassSkill&lt;SpecialSkill&gt;</c>).
/// </para>
/// </remarks>
/// <example>
/// <code>
/// // Attribute-based approach (recommended, AOT-compatible):
/// public class PdfFormatterSkill : AgentClassSkill&lt;PdfFormatterSkill&gt;
/// {
///     public override AgentSkillFrontmatter Frontmatter { get; } = new("pdf-formatter", "Format documents as PDF.");
///     protected override string Instructions =&gt; "Use this skill to format documents...";
///
///     [AgentSkillResource("template")]
///     public string Template =&gt; "Use this template...";
///
///     [AgentSkillScript("format-pdf")]
///     private static string FormatPdf(string content) =&gt; content;
/// }
///
/// // Explicit override approach (AOT-compatible):
/// public class ExplicitPdfFormatterSkill : AgentClassSkill&lt;ExplicitPdfFormatterSkill&gt;
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
public abstract class AgentClassSkill<
    [DynamicallyAccessedMembers(
        DynamicallyAccessedMemberTypes.PublicProperties |
        DynamicallyAccessedMemberTypes.NonPublicProperties |
        DynamicallyAccessedMemberTypes.PublicMethods |
        DynamicallyAccessedMemberTypes.NonPublicMethods)] TSelf>
    : AgentSkill
    where TSelf : AgentClassSkill<TSelf>
{
    private const BindingFlags DiscoveryBindingFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;

    private string? _content;
    private bool _resourcesDiscovered;
    private bool _scriptsDiscovered;
    private IReadOnlyList<AgentSkillResource>? _reflectedResources;
    private IReadOnlyList<AgentSkillScript>? _reflectedScripts;

    /// <summary>
    /// Gets the raw instructions text for this skill.
    /// </summary>
    protected abstract string Instructions { get; }

    /// <summary>
    /// Gets the <see cref="JsonSerializerOptions"/> used to marshal parameters and return values
    /// for scripts and resources.
    /// </summary>
    /// <remarks>
    /// Override this property to provide custom serialization options. This value is used by
    /// reflection-discovered scripts and resources, and also as a fallback by <see cref="CreateScript"/>
    /// and <see cref="CreateResource(string, Delegate, string?, JsonSerializerOptions?)"/> when no
    /// explicit <see cref="JsonSerializerOptions"/> is passed to those methods.
    /// The default value is <see langword="null"/>, which causes <see cref="AIJsonUtilities.DefaultOptions"/> to be used.
    /// </remarks>
    protected virtual JsonSerializerOptions? SerializerOptions => null;

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

    /// <inheritdoc/>
    /// <remarks>
    /// Returns resources discovered via reflection by scanning <typeparamref name="TSelf"/> for
    /// members annotated with <see cref="AgentSkillResourceAttribute"/>. This discovery is
    /// compatible with Native AOT because <typeparamref name="TSelf"/> is annotated with
    /// <see cref="DynamicallyAccessedMembersAttribute"/>. The result is cached after the first access.
    /// </remarks>
    public override IReadOnlyList<AgentSkillResource>? Resources
    {
        get
        {
            if (!this._resourcesDiscovered)
            {
                this._reflectedResources = this.DiscoverResources();
                this._resourcesDiscovered = true;
            }

            return this._reflectedResources;
        }
    }

    /// <inheritdoc/>
    /// <remarks>
    /// Returns scripts discovered via reflection by scanning <typeparamref name="TSelf"/> for
    /// methods annotated with <see cref="AgentSkillScriptAttribute"/>. This discovery is
    /// compatible with Native AOT because <typeparamref name="TSelf"/> is annotated with
    /// <see cref="DynamicallyAccessedMembersAttribute"/>. The result is cached after the first access.
    /// </remarks>
    public override IReadOnlyList<AgentSkillScript>? Scripts
    {
        get
        {
            if (!this._scriptsDiscovered)
            {
                this._reflectedScripts = this.DiscoverScripts();
                this._scriptsDiscovered = true;
            }

            return this._reflectedScripts;
        }
    }

    /// <summary>
    /// Creates a skill resource backed by a static value.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="value">The static resource value.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <returns>A new <see cref="AgentSkillResource"/> instance.</returns>
    protected AgentSkillResource CreateResource(string name, object value, string? description = null)
        => new AgentInlineSkillResource(name, value, description);

    /// <summary>
    /// Creates a skill resource backed by a delegate that produces a dynamic value.
    /// </summary>
    /// <param name="name">The resource name.</param>
    /// <param name="method">A method that produces the resource value when requested.</param>
    /// <param name="description">An optional description of the resource.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the delegate's parameters and return value.
    /// When <see langword="null"/>, falls back to <see cref="SerializerOptions"/>.
    /// </param>
    /// <returns>A new <see cref="AgentSkillResource"/> instance.</returns>
    protected AgentSkillResource CreateResource(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
        => new AgentInlineSkillResource(name, method, description, serializerOptions ?? this.SerializerOptions);

    /// <summary>
    /// Creates a skill script backed by a delegate.
    /// </summary>
    /// <param name="name">The script name.</param>
    /// <param name="method">A method to execute when the script is invoked.</param>
    /// <param name="description">An optional description of the script.</param>
    /// <param name="serializerOptions">
    /// Optional <see cref="JsonSerializerOptions"/> used to marshal the delegate's parameters and return value.
    /// When <see langword="null"/>, falls back to <see cref="SerializerOptions"/>.
    /// </param>
    /// <returns>A new <see cref="AgentSkillScript"/> instance.</returns>
    protected AgentSkillScript CreateScript(string name, Delegate method, string? description = null, JsonSerializerOptions? serializerOptions = null)
        => new AgentInlineSkillScript(name, method, description, serializerOptions ?? this.SerializerOptions);

    private List<AgentSkillResource>? DiscoverResources()
    {
        List<AgentSkillResource>? resources = null;

        var selfType = typeof(TSelf);

        // Discover resources from properties annotated with [AgentSkillResource].
        foreach (var property in selfType.GetProperties(DiscoveryBindingFlags))
        {
            var attr = property.GetCustomAttribute<AgentSkillResourceAttribute>();
            if (attr is null)
            {
                continue;
            }

            var getter = property.GetGetMethod(nonPublic: true);
            if (getter is null)
            {
                continue;
            }

            // Indexer properties have getter parameters and cannot be used as resources
            // because ReadAsync invokes the underlying AIFunction with no named arguments.
            if (getter.GetParameters().Length > 0)
            {
                throw new InvalidOperationException(
                    $"Property '{property.Name}' on type '{selfType.Name}' is an indexer and cannot be used as a skill resource. " +
                    "Remove the [AgentSkillResource] attribute or use a non-indexer property.");
            }

            var name = attr.Name ?? property.Name;
            if (resources?.Exists(r => r.Name == name) == true)
            {
                throw new InvalidOperationException($"Skill '{this.Frontmatter.Name}' already has a resource named '{name}'. Ensure each [AgentSkillResource] has a unique name.");
            }

            resources ??= [];
            resources.Add(new AgentInlineSkillResource(
                name: name,
                method: getter,
                target: getter.IsStatic ? null : this,
                description: property.GetCustomAttribute<DescriptionAttribute>()?.Description,
                serializerOptions: this.SerializerOptions));
        }

        // Discover resources from methods annotated with [AgentSkillResource].
        foreach (var method in selfType.GetMethods(DiscoveryBindingFlags))
        {
            var attr = method.GetCustomAttribute<AgentSkillResourceAttribute>();
            if (attr is null)
            {
                continue;
            }

            ValidateResourceMethodParameters(method, selfType);

            var name = attr.Name ?? method.Name;
            if (resources?.Exists(r => r.Name == name) == true)
            {
                throw new InvalidOperationException($"Skill '{this.Frontmatter.Name}' already has a resource named '{name}'. Ensure each [AgentSkillResource] has a unique name.");
            }

            resources ??= [];
            resources.Add(new AgentInlineSkillResource(
                name: name,
                method: method,
                target: method.IsStatic ? null : this,
                description: method.GetCustomAttribute<DescriptionAttribute>()?.Description,
                serializerOptions: this.SerializerOptions));
        }

        return resources;
    }

    private static void ValidateResourceMethodParameters(MethodInfo method, Type skillType)
    {
        foreach (var param in method.GetParameters())
        {
            if (param.ParameterType != typeof(IServiceProvider) &&
                param.ParameterType != typeof(CancellationToken))
            {
                throw new InvalidOperationException(
                    $"Method '{method.Name}' on type '{skillType.Name}' has parameter '{param.Name}' of type " +
                    $"'{param.ParameterType}' which cannot be supplied when reading a resource. " +
                    "Resource methods may only accept IServiceProvider and/or CancellationToken parameters. " +
                    "Remove the [AgentSkillResource] attribute or change the method signature.");
            }
        }
    }

    private List<AgentSkillScript>? DiscoverScripts()
    {
        List<AgentSkillScript>? scripts = null;

        foreach (var method in typeof(TSelf).GetMethods(DiscoveryBindingFlags))
        {
            var attr = method.GetCustomAttribute<AgentSkillScriptAttribute>();
            if (attr is null)
            {
                continue;
            }

            var name = attr.Name ?? method.Name;
            if (scripts?.Exists(s => s.Name == name) == true)
            {
                throw new InvalidOperationException($"Skill '{this.Frontmatter.Name}' already has a script named '{name}'. Ensure each [AgentSkillScript] has a unique name.");
            }

            scripts ??= [];
            scripts.Add(new AgentInlineSkillScript(
                name: name,
                method: method,
                target: method.IsStatic ? null : this,
                description: method.GetCustomAttribute<DescriptionAttribute>()?.Description,
                serializerOptions: this.SerializerOptions));
        }

        return scripts;
    }
}
