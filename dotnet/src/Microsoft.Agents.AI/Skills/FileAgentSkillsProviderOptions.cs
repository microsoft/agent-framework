// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="FileAgentSkillsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkillsProviderOptions
{
    /// <summary>
    /// Gets or sets a custom system prompt template for advertising skills.
    /// Use <c>{skills}</c> as the placeholder for the generated skills list and
    /// <c>{executor_instructions}</c> for executor-provided instructions.
    /// When <see langword="null"/>, a default template is used.
    /// </summary>
    public string? SkillsInstructionPrompt { get; set; }

    /// <summary>
    /// Gets or sets the skill executor that enables script execution for loaded skills.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> (the default), script execution is disabled and skills only provide
    /// instructions and resources. Set this to a <see cref="FileAgentSkillScriptExecutor"/> instance (e.g.,
    /// <see cref="FileAgentSkillScriptExecutor.HostedCodeInterpreter()"/>) to enable script execution with
    /// mode-specific instructions and tools.
    /// </remarks>
    public FileAgentSkillScriptExecutor? ScriptExecutor { get; set; }
}
