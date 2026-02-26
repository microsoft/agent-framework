// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the tools and instructions contributed by a <see cref="FileAgentSkillScriptExecutor"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkillScriptExecutionDetails
{
    /// <summary>
    /// Gets the additional instructions to provide to the agent for script execution.
    /// </summary>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets the additional tools to provide to the agent for script execution.
    /// </summary>
    public IReadOnlyList<AITool>? Tools { get; set; }
}
