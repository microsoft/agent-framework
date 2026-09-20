// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Specifies how a <see cref="DecisionLoopEvaluator"/> reacts when the decision client fails operationally (for
/// example a provider, network, or protocol error, or an invalid probability) rather than returning a probability.
/// </summary>
/// <remarks>
/// An operational failure is not a semantic answer: it does not mean the task is incomplete. The default,
/// <see cref="Throw"/>, surfaces the failure to the caller. The other behaviors let an application choose an explicit
/// policy instead. No behavior is ever selected implicitly based on the provider.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum DecisionLoopFailureBehavior
{
    /// <summary>Propagate the failure to the caller of the loop. This is the default.</summary>
    Throw = 0,

    /// <summary>
    /// Request another iteration, carrying the configured
    /// <see cref="DecisionLoopEvaluatorOptions.ContinueFeedbackMessage"/> as feedback. The loop remains bounded by
    /// <see cref="LoopAgentOptions.MaxIterations"/>.
    /// </summary>
    Continue = 1,

    /// <summary>
    /// Return <see cref="LoopEvaluation.Stop"/> so that later evaluators configured on the <see cref="LoopAgent"/> decide
    /// instead. Because <see cref="LoopEvaluation.Stop"/> only means "this evaluator does not request another iteration",
    /// the loop ends when the decision evaluator is the last (or only) evaluator and no other evaluator requests
    /// continuation.
    /// </summary>
    DeferToNextEvaluator = 2,
}
