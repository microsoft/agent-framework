// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides the abstract base class for the component that decides, after each agent iteration, whether a
/// <see cref="LoopAgent"/> should re-invoke the wrapped agent and what feedback to provide.
/// </summary>
/// <remarks>
/// <para>
/// A <see cref="LoopEvaluator"/> is pure judgment: it inspects the <see cref="LoopContext"/> and returns a
/// <see cref="LoopEvaluation"/> describing whether to continue and any feedback for the next iteration. It does not
/// manage the session or construct the next input messages — that is the responsibility of the
/// <see cref="LoopAgent"/> that consumes it.
/// </para>
/// <para>
/// Out-of-the-box implementations include <see cref="AIJudgeLoopEvaluator"/>, <see cref="DelegateLoopEvaluator"/>,
/// <see cref="CompletionMarkerLoopEvaluator"/>, and <see cref="TodoCompletionLoopEvaluator"/>. Implementations should be stateless and safe to share across
/// concurrent loop runs; any per-run state must be stored on the supplied <see cref="LoopContext"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class LoopEvaluator
{
    /// <summary>
    /// Evaluates the loop state after an iteration and decides whether to re-invoke the wrapped agent and what
    /// feedback to provide.
    /// </summary>
    /// <param name="context">The per-run <see cref="LoopContext"/> describing the current loop state.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A value task whose result is a <see cref="LoopEvaluation"/> indicating whether to continue and, if so, the
    /// feedback to carry forward to the next iteration.
    /// </returns>
    public abstract ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default);
}
