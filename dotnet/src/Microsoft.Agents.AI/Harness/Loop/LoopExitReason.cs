// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides typed exit-reason strings for <see cref="LoopAgent"/> runs.
/// Values are plain strings to remain JSON-transparent. The reason is surfaced under
/// <see cref="AdditionalPropertiesKey"/> in <c>AgentResponse.AdditionalProperties</c>.
/// </summary>
/// <remarks>
/// <para>
/// Exit reasons are stamped by <see cref="LoopAgent"/> on <strong>non-streaming</strong> runs only.
/// In streaming mode the response is assembled from yielded updates by the caller, so there is no
/// single <c>AgentResponse</c> object available inside the generator to stamp.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class LoopExitReason
{
    /// <summary>The key used in <c>AgentResponse.AdditionalProperties</c> to surface the loop exit reason.</summary>
    public const string AdditionalPropertiesKey = "loop_exit_reason";

    /// <summary>The <see cref="LoopAgentOptions.MaxIterations"/> cap was reached before the evaluators stopped the loop.</summary>
    public const string IterationCapReached = "iteration_cap_reached";

    /// <summary>The token budget (<see cref="LoopAgentOptions.MaxTokens"/>) was exhausted before the loop completed.</summary>
    public const string TokenBudgetExceeded = "token_budget_exceeded";

    /// <summary>The wall-clock time budget (<see cref="LoopAgentOptions.MaxDuration"/>) was exhausted before the loop completed.</summary>
    public const string TimeBudgetExceeded = "time_budget_exceeded";
}
