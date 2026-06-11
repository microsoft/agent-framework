// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="LoopEvaluator"/> that uses a separate judge chat client to decide whether the user's original request
/// has been fully addressed, continuing the loop (with the judge's gap analysis as feedback) while the answer is "no".
/// </summary>
/// <remarks>
/// <para>
/// After each iteration the judge is queried directly (without any agent tools, session, or middleware) with the
/// original request and the agent's latest response, and asked for a structured <see cref="JudgeVerdict"/>. If the
/// judge client does not honor structured output, the verdict falls back to parsing the raw text for the
/// non-overlapping <see cref="DoneVerdictMarker"/> / <see cref="MoreVerdictMarker"/> markers (with
/// <see cref="MoreVerdictMarker"/> winning, so the loop keeps running, when the verdict is ambiguous or absent).
/// </para>
/// <para>
/// When the request is not yet answered, the evaluator returns feedback built from
/// <see cref="AIJudgeLoopEvaluatorOptions.FeedbackMessageTemplate"/> with the judge's gap analysis substituted for
/// <see cref="GapAnalysisPlaceholder"/>. How that feedback is delivered to the agent (and whether the session is
/// reset) is decided by the <see cref="LoopAgent"/> that consumes this evaluator.
/// </para>
/// <para>
/// The judge instructions act as a template: any occurrence of <see cref="CriteriaPlaceholder"/> is replaced with the
/// rendered <see cref="AIJudgeLoopEvaluatorOptions.Criteria"/> (or removed when no criteria are supplied), letting
/// callers add bespoke standards the response must satisfy.
/// </para>
/// <para>
/// LLM-judged loops are costly and probabilistic, so consider setting a stricter
/// <see cref="LoopAgentOptions.MaxIterations"/> on the owning <see cref="LoopAgent"/>.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AIJudgeLoopEvaluator : LoopEvaluator
{
    /// <summary>The default system instructions used to prompt the judge.</summary>
    /// <remarks>
    /// Acts as a template: the trailing <see cref="CriteriaPlaceholder"/> is replaced with the rendered
    /// <see cref="AIJudgeLoopEvaluatorOptions.Criteria"/> (or removed when none are supplied).
    /// </remarks>
    public const string DefaultInstructions =
        "You are an evaluator. You are given a user's original request and an agent's latest response. " +
        "Decide whether the agent has fully addressed the original request. " +
        "Set 'answered' to true if the request has been fully addressed, or false if more work is still required. " +
        "When 'answered' is false, use 'gapAnalysis' to explain what is still missing or what work remains. " +
        "If you cannot return structured output, reply with " + DoneVerdictMarker + " when the request has been fully " +
        "addressed, or " + MoreVerdictMarker + " when more work is still required." +
        CriteriaPlaceholder;

    /// <summary>
    /// The verdict marker the judge is asked to emit (for clients that do not honor structured output) when the
    /// original request has been fully addressed.
    /// </summary>
    /// <remarks>
    /// <see cref="DoneVerdictMarker"/> and <see cref="MoreVerdictMarker"/> are deliberately non-overlapping (neither is
    /// a substring of the other), so the text fallback cannot misclassify one verdict as the other. When the marker is
    /// ambiguous or absent, <see cref="MoreVerdictMarker"/> wins so the loop keeps running rather than stopping on an
    /// incomplete answer.
    /// </remarks>
    public const string DoneVerdictMarker = "VERDICT: DONE";

    /// <summary>
    /// The verdict marker the judge is asked to emit (for clients that do not honor structured output) when more work
    /// is still required. Takes precedence over <see cref="DoneVerdictMarker"/> when both (or neither) are present.
    /// </summary>
    public const string MoreVerdictMarker = "VERDICT: MORE";

    /// <summary>
    /// The placeholder token within <see cref="DefaultInstructions"/> (or a custom
    /// <see cref="AIJudgeLoopEvaluatorOptions.Instructions"/>) that is replaced with the rendered
    /// <see cref="AIJudgeLoopEvaluatorOptions.Criteria"/>. When no criteria are supplied, the placeholder is removed.
    /// </summary>
    public const string CriteriaPlaceholder = "{criteria}";

    /// <summary>
    /// The placeholder token within <see cref="DefaultFeedbackMessageTemplate"/> (or a custom
    /// <see cref="AIJudgeLoopEvaluatorOptions.FeedbackMessageTemplate"/>) that is replaced with the judge's gap analysis.
    /// </summary>
    public const string GapAnalysisPlaceholder = "{gap_analysis}";

    /// <summary>The default template used to build the feedback produced when the request is not yet answered.</summary>
    public const string DefaultFeedbackMessageTemplate =
        "Your previous response did not fully address the original request. " +
        "The following is still missing or incomplete: " + GapAnalysisPlaceholder + " " +
        "Please continue and fully address the original request.";

    /// <summary>The value substituted for the gap analysis when the judge did not provide one.</summary>
    private const string UnknownGapAnalysis = "<unknown>";

    private readonly IChatClient _judgeClient;
    private readonly string _instructions;
    private readonly string _feedbackMessageTemplate;

    /// <summary>
    /// Initializes a new instance of the <see cref="AIJudgeLoopEvaluator"/> class.
    /// </summary>
    /// <param name="judgeClient">The chat client used to judge whether the original request was answered.</param>
    /// <param name="options">Optional configuration for the judge. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException"><paramref name="judgeClient"/> is <see langword="null"/>.</exception>
    public AIJudgeLoopEvaluator(IChatClient judgeClient, AIJudgeLoopEvaluatorOptions? options = null)
    {
        this._judgeClient = Throw.IfNull(judgeClient);
        this._instructions = (options?.Instructions ?? DefaultInstructions)
            .Replace(CriteriaPlaceholder, RenderCriteria(options?.Criteria));
        this._feedbackMessageTemplate = options?.FeedbackMessageTemplate ?? DefaultFeedbackMessageTemplate;
    }

    /// <inheritdoc />
    public override async ValueTask<LoopEvaluation> EvaluateAsync(LoopContext context, CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(context);

        // Build the judge's user message from AIContent so non-text request content (images, data, etc.) is
        // preserved rather than flattened to text. The original request's contents are framed between header
        // text segments, followed by the agent's latest response text.
        var userContents = new List<AIContent>
        {
            new TextContent("# Has the original request been fully addressed?\n\n## Original request:\n"),
        };
        foreach (ChatMessage message in context.InitialMessages)
        {
            userContents.AddRange(message.Contents);
        }

        userContents.Add(new TextContent($"\n\n## Agent's latest response:\n{context.LastResponse.Text}"));

        List<ChatMessage> judgeMessages =
        [
            new ChatMessage(ChatRole.System, this._instructions),
            new ChatMessage(ChatRole.User, userContents),
        ];

        bool answered;
        string gapAnalysis = UnknownGapAnalysis;
        ChatResponse<JudgeVerdict> response = await this._judgeClient
            .GetResponseAsync<JudgeVerdict>(judgeMessages, LoopJsonContext.Default.Options, cancellationToken: cancellationToken)
            .ConfigureAwait(false);

        if (response.TryGetResult(out JudgeVerdict? verdict) && verdict is not null)
        {
            answered = verdict.Answered;
            if (!string.IsNullOrWhiteSpace(verdict.GapAnalysis))
            {
                gapAnalysis = verdict.GapAnalysis;
            }
        }
        else
        {
            // Fallback for clients that do not honor structured output: look for the explicit, non-overlapping verdict
            // markers. MoreVerdictMarker wins so an ambiguous or marker-less reply keeps looping rather than stopping
            // on an incomplete answer.
            string text = response.Text.ToUpperInvariant();
            answered = !text.Contains(MoreVerdictMarker) && text.Contains(DoneVerdictMarker);
        }

        // The request is answered: stop looping.
        if (answered)
        {
            return LoopEvaluation.Stop();
        }

        // Not yet answered: continue, providing feedback describing what is still missing.
        string feedback = this._feedbackMessageTemplate.Replace(GapAnalysisPlaceholder, gapAnalysis);
        return LoopEvaluation.Continue(feedback);
    }

    /// <summary>
    /// Renders the supplied <paramref name="criteria"/> into a bullet block appended at <see cref="CriteriaPlaceholder"/>,
    /// or an empty string when no non-blank criteria are supplied.
    /// </summary>
    private static string RenderCriteria(IEnumerable<string>? criteria)
    {
        if (criteria is null)
        {
            return string.Empty;
        }

        var builder = new StringBuilder();
        foreach (string criterion in criteria)
        {
            if (!string.IsNullOrWhiteSpace(criterion))
            {
                builder.Append("\n- ").Append(criterion);
            }
        }

        return builder.Length == 0
            ? string.Empty
            : "\n\nThe response must satisfy all of the following criteria:" + builder;
    }
}
