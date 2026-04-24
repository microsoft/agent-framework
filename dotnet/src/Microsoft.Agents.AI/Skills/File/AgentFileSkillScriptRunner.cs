// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Delegate for running file-based skill scripts.
/// </summary>
/// <remarks>
/// Implementations determine the execution strategy (e.g., local subprocess, hosted code execution environment).
/// The <paramref name="arguments"/> parameter preserves the raw JSON format sent by the caller,
/// which may be a JSON array (for positional CLI arguments) or a JSON object (for named parameters).
/// </remarks>
/// <param name="skill">The skill that owns the script.</param>
/// <param name="script">The file-based script to run.</param>
/// <param name="arguments">Raw JSON arguments for the script, preserving the original format (object or array) sent by the caller.</param>
/// <param name="serviceProvider">Optional service provider for dependency injection.</param>
/// <param name="cancellationToken">Cancellation token.</param>
/// <returns>The script execution result.</returns>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public delegate Task<object?> AgentFileSkillScriptRunner(
    AgentFileSkill skill,
    AgentFileSkillScript script,
    JsonElement? arguments,
    IServiceProvider? serviceProvider,
    CancellationToken cancellationToken);
