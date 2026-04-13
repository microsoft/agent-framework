// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Delegate for running file-based skill scripts.
/// </summary>
/// <remarks>
/// Implementations determine the execution strategy (e.g., local subprocess, hosted code execution environment).
/// </remarks>
/// <param name="skill">The skill that owns the script.</param>
/// <param name="script">The file-based script to run.</param>
/// <param name="arguments">Optional arguments for the script, provided by the agent/LLM.</param>
/// <param name="cancellationToken">Cancellation token.</param>
/// <returns>The script execution result.</returns>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public delegate Task<object?> AgentFileSkillScriptRunner(
    AgentFileSkill skill,
    AgentFileSkillScript script,
    AIFunctionArguments arguments,
    CancellationToken cancellationToken);
