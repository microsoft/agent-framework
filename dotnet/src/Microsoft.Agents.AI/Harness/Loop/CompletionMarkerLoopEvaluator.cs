// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> that stops the loop once a configured marker string appears in the agent's latest
/// response, and otherwise continues with feedback asking the agent to keep working and to emit the marker when done.
/// </summary>
/// <remarks>
/// The feedback produced while the marker is absent is built from a template (see
/// <see cref="CompletionMarkerLoopEvaluatorOptions.FeedbackMessageTemplate"/>) with the configured marker substituted
/// for <see cref="CompletionMarkerPlaceholder"/>, and the agent's latest response text substituted for
/// <see cref="LastResponsePlaceholder"/>. How that feedback is delivered to the agent (and whether the session
/// is reset) is decided by the <see cref="LoopAgent"/> that consumes this evaluator.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class CompletionMarkerLoopEvaluator : LoopEvaluator
{
    /// <summary>
    /// The placeholder token within <see cref="DefaultFeedbackMessageTemplate"/> (or a custom
    /// <see cref="CompletionMarkerLoopEvaluatorOptions.FeedbackMessageTemplate"/>) that is replaced with the
    /// configured completion marker.
    /// </summary>
    public const string CompletionMarkerPlaceholder = "{completion_marker}";

    /// <summary>
    /// The placeholder token within a custom <see cref="CompletionMarkerLoopEvaluatorOptions.FeedbackMessageTemplate"/>
    /// that is replaced with the text of the agent's latest response. This is substituted on each evaluation, so it lets
    /// the feedback echo back what the agent previously produced — useful when the consuming
    /// <see cref="LoopAgent"/> uses <see cref="LoopAgentOptions.FreshContextPerIteration"/>, where the agent would
    /// otherwise have no record of its prior output.
    /// </summary>
    public const string LastResponsePlaceholder = "{last_response}";

    /// <summary>The default template used to build the feedback produced while the completion marker is absent.</summary>
    public const string DefaultFeedbackMessageTemplate =
        "Continue working on the request. When you have fully completed the task, end your response with the marker '" +
        CompletionMarkerPlaceholder + "' to indicate completion.";

    private readonly string _completionMarker;
    private readonly string _feedbackMessageTemplate;

    /// <summary>
    /// Initializes a new instance of the <see cref="CompletionMarkerLoopEvaluator"/> class.
    /// </summary>
    /// <param name="completionMarker">The marker string that stops the loop once it appears in the agent's latest response text.</param>
    /// <param name="options">Optional configuration for the feedback message. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="System.ArgumentException"><paramref name="completionMarker"/> is <see langword="null"/>, empty, or whitespace.</exception>
    public CompletionMarkerLoopEvaluator(string completionMarker, CompletionMarkerLoopEvaluatorOptions? options = null)
    {
        this._completionMarker = Throw.IfNullOrWhitespace(completionMarker);

        // The completion marker is fixed, so substitute it once here. The optional {last_response} placeholder depends
        // on the per-iteration response text, so it is substituted later in EvaluateAsync.
        this._feedbackMessageTemplate = (options?.FeedbackMessageTemplate ?? DefaultFeedbackMessageTemplate)
            .Replace(CompletionMarkerPlaceholder, this._completionMarker);
    }

    /// <inheritdoc />
    public override ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        if (context.LastResponse.Text.Contains(this._completionMarker))
        {
            return new ValueTask<LoopEvaluation>(LoopEvaluation.Stop());
        }

        string feedback = this._feedbackMessageTemplate.Replace(LastResponsePlaceholder, context.LastResponse.Text);
        return new ValueTask<LoopEvaluation>(LoopEvaluation.Continue(feedback));
    }
}
