// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Marks a property or method as a skill resource that is automatically discovered by <see cref="AgentClassSkill{TSelf}"/>.
/// </summary>
/// <remarks>
/// <para>
/// Apply this attribute to properties or methods in an <see cref="AgentClassSkill{TSelf}"/> subclass to register
/// them as skill resources.
/// </para>
/// <para>
/// To provide a description for the resource, apply <see cref="DescriptionAttribute"/>
/// to the same member.
/// </para>
/// <para>
/// When applied to a <b>property</b>, the property getter is invoked each time the resource is read,
/// enabling dynamic (computed) resources. When applied to a <b>method</b>, the method is invoked each time
/// the resource is read, also enabling dynamic resources. Methods with an
/// <see cref="IServiceProvider"/> parameter support dependency injection.
/// </para>
/// <para>
/// This attribute is compatible with Native AOT when used with <see cref="AgentClassSkill{TSelf}"/>.
/// Alternatively, override the <see cref="AgentSkill.Resources"/> property and use
/// <see cref="AgentClassSkill{TSelf}.CreateResource(string, object, string?)"/> instead.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// public class MySkill : AgentClassSkill&lt;MySkill&gt;
/// {
///     public override AgentSkillFrontmatter Frontmatter { get; } = new("my-skill", "A skill.");
///     protected override string Instructions =&gt; "Use this skill to do something.";
///
///     [AgentSkillResource("reference-data")]
///     [Description("Some reference content for the skill.")]
///     public string ReferenceData =&gt; "Some reference content.";
/// }
/// </code>
/// </example>
[AttributeUsage(AttributeTargets.Property | AttributeTargets.Method, AllowMultiple = false, Inherited = false)]
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillResourceAttribute : Attribute
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillResourceAttribute"/> class.
    /// The resource name defaults to the property or method name.
    /// </summary>
    public AgentSkillResourceAttribute()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillResourceAttribute"/> class
    /// with an explicit resource name.
    /// </summary>
    /// <param name="name">The resource name used to identify this resource.</param>
    public AgentSkillResourceAttribute(string name)
    {
        this.Name = name;
    }

    /// <summary>
    /// Gets the resource name, or <see langword="null"/> to use the member name.
    /// </summary>
    public string? Name { get; }
}
