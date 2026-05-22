// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Marks a method as a skill script that is automatically discovered by <see cref="AgentClassSkill{TSelf}"/>.
/// </summary>
/// <remarks>
/// <para>
/// Apply this attribute to methods in an <see cref="AgentClassSkill{TSelf}"/> subclass to register them as
/// skill scripts. The method's parameters and return type are automatically marshaled via
/// <c>AIFunctionFactory</c>.
/// </para>
/// <para>
/// To provide a description for the script, apply <see cref="DescriptionAttribute"/>
/// to the same method.
/// </para>
/// <para>
/// Methods can be instance or static, and may have any visibility (public, private, etc.).
/// Methods with an <see cref="IServiceProvider"/> parameter support dependency injection.
/// </para>
/// <para>
/// This attribute is compatible with Native AOT when used with <see cref="AgentClassSkill{TSelf}"/>.
/// Alternatively, override the <see cref="AgentSkill.Scripts"/> property and use
/// <see cref="AgentClassSkill{TSelf}.CreateScript"/> instead.
/// </para>
/// </remarks>
/// <example>
/// <code>
/// public class MySkill : AgentClassSkill&lt;MySkill&gt;
/// {
///     public override AgentSkillFrontmatter Frontmatter { get; } = new("my-skill", "A skill.");
///     protected override string Instructions =&gt; "Use this skill to do something.";
///
///     [AgentSkillScript("do-something")]
///     [Description("Converts the input to upper case.")]
///     private static string DoSomething(string input) =&gt; input.ToUpperInvariant();
/// }
/// </code>
/// </example>
[AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)]
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillScriptAttribute : Attribute
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillScriptAttribute"/> class.
    /// The script name defaults to the method name.
    /// </summary>
    public AgentSkillScriptAttribute()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentSkillScriptAttribute"/> class
    /// with an explicit script name.
    /// </summary>
    /// <param name="name">The script name used to identify this script.</param>
    public AgentSkillScriptAttribute(string name)
    {
        this.Name = name;
    }

    /// <summary>
    /// Gets the script name, or <see langword="null"/> to use the method name.
    /// </summary>
    public string? Name { get; }
}
