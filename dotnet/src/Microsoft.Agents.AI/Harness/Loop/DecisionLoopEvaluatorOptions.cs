// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides configuration options for <see cref="DecisionLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionLoopEvaluatorOptions
{
    /// <summary>
    /// Gets or sets the model-reported probability of completion at or above which the evaluator stops requesting
    /// iterations. Defaults to <see cref="DecisionLoopEvaluator.DefaultCompletionThreshold"/>.
    /// </summary>
    /// <remarks>
    /// The threshold is application policy, not a property of the decision source. A false stop returns an incomplete
    /// result while a false continue only costs another iteration, so a deliberately high threshold is usually the
    /// safer choice. Must be between 0 and 1 inclusive.
    /// </remarks>
    public double CompletionThreshold { get; set; } = DecisionLoopEvaluator.DefaultCompletionThreshold;

    /// <summary>
    /// Gets or sets the yes/no proposition sent to the decision client. Defaults to
    /// <see cref="DecisionLoopEvaluator.DefaultCompletionQuestion"/>.
    /// </summary>
    /// <remarks>
    /// Phrase it so that a high probability means the loop should stop. A <see langword="null"/> value falls back to the
    /// default; an empty or whitespace value is rejected by the evaluator constructor.
    /// </remarks>
    public string CompletionQuestion { get; set; } = DecisionLoopEvaluator.DefaultCompletionQuestion;

    /// <summary>
    /// Gets or sets an optional description of what a "yes" (completed) answer means, sent to the decision client as
    /// <see cref="BinaryDecisionCriteria.TrueDescription"/>. Defaults to
    /// <see cref="DecisionLoopEvaluator.DefaultCompletedDescription"/>; set to <see langword="null"/> to omit it.
    /// </summary>
    public string? CompletedDescription { get; set; } = DecisionLoopEvaluator.DefaultCompletedDescription;

    /// <summary>
    /// Gets or sets an optional description of what a "no" (incomplete) answer means, sent to the decision client as
    /// <see cref="BinaryDecisionCriteria.FalseDescription"/>. Defaults to
    /// <see cref="DecisionLoopEvaluator.DefaultIncompleteDescription"/>; set to <see langword="null"/> to omit it.
    /// </summary>
    public string? IncompleteDescription { get; set; } = DecisionLoopEvaluator.DefaultIncompleteDescription;

    /// <summary>
    /// Gets or sets the feedback carried into the next iteration when the evaluator decides the request is not yet
    /// complete. Defaults to <see cref="DecisionLoopEvaluator.DefaultContinueFeedbackMessage"/>.
    /// </summary>
    /// <remarks>
    /// A decision model reports a probability, not an explanation, so this text is deterministic application text rather
    /// than model output. Set it to <see langword="null"/> or whitespace to continue without feedback; note that in the
    /// default reused-session mode the <see cref="LoopAgent"/> then re-invokes the agent with no new input messages.
    /// </remarks>
    public string? ContinueFeedbackMessage { get; set; } = DecisionLoopEvaluator.DefaultContinueFeedbackMessage;

    /// <summary>
    /// Gets or sets a factory that builds the serialized state sent to the decision client from the current
    /// <see cref="LoopContext"/>, replacing the evaluator's default projection.
    /// </summary>
    /// <remarks>
    /// The default projection contains only the text of the original request messages, the latest response text, and
    /// the iteration number, and it rejects requests containing non-text content. Supply a factory to judge different or
    /// richer state (for example a textual rendering of images, or additional session facts). The application owns
    /// whatever additional data the factory chooses to disclose to the decision source.
    /// </remarks>
    public Func<LoopContext, JsonElement>? StateFactory { get; set; }

    /// <summary>
    /// Gets or sets how the evaluator reacts when the decision client fails operationally. Defaults to
    /// <see cref="DecisionLoopFailureBehavior.Throw"/>.
    /// </summary>
    public DecisionLoopFailureBehavior FailureBehavior { get; set; } = DecisionLoopFailureBehavior.Throw;

    /// <summary>
    /// Gets or sets how the evaluator reacts when the decision client reports a failure it classifies as transient
    /// (<see cref="DecisionClientException.IsTransient"/>: rate limiting, overload, or a provider-side outage), or
    /// <see langword="null"/> to apply <see cref="FailureBehavior"/> to those failures as well. Defaults to <see langword="null"/>.
    /// </summary>
    /// <remarks>
    /// This lets a loop survive a momentary provider hiccup (for example continue, or defer to a later evaluator) while
    /// still surfacing permanent problems such as a rejected API key or an invalid request through <see cref="FailureBehavior"/>.
    /// Any retry-like effect stays visible: the applied policy is logged at warning level when a logger is configured.
    /// </remarks>
    public DecisionLoopFailureBehavior? TransientFailureBehavior { get; set; }
}
