// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="AgentSkillsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentSkillsProviderOptions
{
    /// <summary>
    /// Gets or sets a custom system prompt template for advertising skills.
    /// The template must contain <c>{skills}</c> as the placeholder for the generated skills list,
    /// <c>{resource_instructions}</c> for resource instructions,
    /// and <c>{script_instructions}</c> for script instructions.
    /// When <see langword="null"/>, a default template is used.
    /// </summary>
    public string? SkillsInstructionPrompt { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether script execution requires approval.
    /// When <see langword="true"/>, script execution is blocked until approved.
    /// Defaults to <see langword="false"/>.
    /// </summary>
    public bool ScriptApproval { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether caching of tools and instructions is disabled.
    /// When <see langword="false"/> (the default), the provider caches the tools and instructions
    /// after the first build and returns the cached instance on subsequent calls.
    /// Set to <see langword="true"/> to rebuild tools and instructions on every invocation.
    /// </summary>
    public bool DisableCaching { get; set; }
}
