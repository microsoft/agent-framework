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
    /// The template must contain <c>{skills}</c> as the placeholder for the generated skills list
    /// and <c>{runner_instructions}</c> for script runner instructions.
    /// When <see langword="null"/>, a default template is used.
    /// </summary>
    public string? SkillsInstructionPrompt { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether script execution requires approval.
    /// When <see langword="true"/>, script execution is blocked until approved.
    /// Defaults to <see langword="false"/>.
    /// </summary>
    public bool ScriptApproval { get; set; }
}
