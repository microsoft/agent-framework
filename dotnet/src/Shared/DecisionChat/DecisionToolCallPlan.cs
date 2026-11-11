// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// The internal questions that let a decision model choose one tool call, and the decoders that turn their answers into
/// the call.
/// </summary>
internal sealed class DecisionToolCallPlan
{
    /// <summary>
    /// A Binary answer above this probability means yes, for presence, Boolean, and array member questions.
    /// </summary>
    public const double YesThreshold = 0.5;

    /// <summary>Gets the internal questions by ID, in the order they are asked.</summary>
    public required IReadOnlyDictionary<string, DecisionQuestion> Questions { get; init; }

    public required IReadOnlyList<DecisionCompiledTool> Tools { get; init; }

    /// <summary>
    /// Gets the ID of the Choice question that selects the tool, or <see langword="null"/> when
    /// <see cref="RequiredTool"/> is the only possible call.
    /// </summary>
    public string? RouteQuestionId { get; init; }

    /// <summary>
    /// Gets the tool that must be called, when the tool mode requires a call and only one tool compiled.
    /// </summary>
    public DecisionCompiledTool? RequiredTool { get; init; }

    /// <summary>
    /// Reads the selected tool call from the answers.
    /// </summary>
    /// <returns>The tool call, or <see langword="null"/> when the model chose not to call a tool.</returns>
    public DecisionToolCall? Decode(DecisionResponse response)
    {
        DecisionCompiledTool? selected = this.RequiredTool;
        if (selected is null)
        {
            string route = GetChoice(response, this.RouteQuestionId!);
            if (string.Equals(route, DecisionToolCallCompiler.RouteNone, StringComparison.Ordinal))
            {
                return null;
            }

            selected = this.Tools.FirstOrDefault(tool => string.Equals(tool.RouteLabel, route, StringComparison.Ordinal))
                ?? throw new InvalidOperationException($"The decision model returned the unknown tool route '{route}'.");
        }

        return new DecisionToolCall(selected.Function, selected.DecodeArguments(response));
    }

    public static string GetChoice(DecisionResponse response, string questionId) =>
        FindAnswer(response, questionId) is ChoiceDecisionAnswer choice
            ? choice.SelectedCandidateId
            : throw new InvalidOperationException($"The decision response has no Choice answer for the internal question '{questionId}'.");

    public static bool IsYes(DecisionResponse response, string questionId) =>
        FindAnswer(response, questionId) is BinaryDecisionAnswer binary
            ? binary.TrueProbability > YesThreshold
            : throw new InvalidOperationException($"The decision response has no Binary answer for the internal question '{questionId}'.");

    private static DecisionAnswer? FindAnswer(DecisionResponse response, string questionId)
    {
        foreach (DecisionAnswer answer in response.Answers)
        {
            if (string.Equals(answer.QuestionId, questionId, StringComparison.Ordinal))
            {
                return answer;
            }
        }

        return null;
    }
}
