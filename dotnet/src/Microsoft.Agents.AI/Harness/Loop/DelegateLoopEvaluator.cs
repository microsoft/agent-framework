// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> that delegates the re-invocation decision and feedback to a user-supplied callback.
/// </summary>
/// <remarks>
/// This is the most flexible evaluator: the supplied delegate receives the full <see cref="LoopContext"/> and returns
/// a <see cref="LoopEvaluation"/>, so it can decide both whether to continue and what feedback (if any) to provide.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DelegateLoopEvaluator : LoopEvaluator
{
    private readonly Func<LoopContext, CancellationToken, ValueTask<LoopEvaluation>> _evaluate;

    /// <summary>
    /// Initializes a new instance of the <see cref="DelegateLoopEvaluator"/> class.
    /// </summary>
    /// <param name="evaluate">A callback that decides whether to re-invoke the agent and what feedback to provide.</param>
    /// <exception cref="ArgumentNullException"><paramref name="evaluate"/> is <see langword="null"/>.</exception>
    public DelegateLoopEvaluator(Func<LoopContext, CancellationToken, ValueTask<LoopEvaluation>> evaluate)
    {
        this._evaluate = Throw.IfNull(evaluate);
    }

    /// <inheritdoc />
    public override ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);
        return this._evaluate(context, cancellationToken);
    }
}
