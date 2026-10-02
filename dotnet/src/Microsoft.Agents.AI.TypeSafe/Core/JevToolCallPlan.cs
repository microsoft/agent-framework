// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The internal questions that let Jev choose one tool call, and the decoders that turn their answers into the call.
/// </summary>
internal sealed class JevToolCallPlan
{
    /// <summary>
    /// A Noul answer above this probability means yes, for presence, Boolean, and array member questions.
    /// </summary>
    public const double NoulYesThreshold = 0.5;

    public required IReadOnlyDictionary<string, JevQuestion> Questions { get; init; }

    public required IReadOnlyList<JevCompiledTool> Tools { get; init; }

    /// <summary>
    /// Gets the ID of the Choice question that selects the tool, or <see langword="null"/> when
    /// <see cref="RequiredTool"/> is the only possible call.
    /// </summary>
    public string? RouteQuestionId { get; init; }

    /// <summary>
    /// Gets the tool that must be called, when the tool mode requires a call and only one tool compiled.
    /// </summary>
    public JevCompiledTool? RequiredTool { get; init; }

    /// <summary>
    /// Reads the selected tool call from Jev's answers.
    /// </summary>
    /// <returns>The tool call, or <see langword="null"/> when Jev chose not to call a tool.</returns>
    public JevToolCall? Decode(JevResult result)
    {
        JevCompiledTool? selected = this.RequiredTool;
        if (selected is null)
        {
            string route = GetChoice(result, this.RouteQuestionId!);
            if (route == JevToolCallCompiler.RouteNone)
            {
                return null;
            }

            selected = this.Tools.FirstOrDefault(tool => tool.RouteLabel == route)
                ?? throw new InvalidOperationException($"Jev returned the unknown tool route '{route}'.");
        }

        return new JevToolCall(selected.Function, selected.DecodeArguments(result));
    }

    public static string GetChoice(JevResult result, string questionId) =>
        result.Answers.TryGetValue(questionId, out JevResponse? answer) && answer is JevChoiceResponse choice
            ? choice.Choice
            : throw new InvalidOperationException($"The Jev result has no Choice answer for the internal question '{questionId}'.");

    public static bool IsYes(JevResult result, string questionId) =>
        result.Answers.TryGetValue(questionId, out JevResponse? answer) && answer is JevNoulResponse noul
            ? noul.Noul > NoulYesThreshold
            : throw new InvalidOperationException($"The Jev result has no Noul answer for the internal question '{questionId}'.");
}
