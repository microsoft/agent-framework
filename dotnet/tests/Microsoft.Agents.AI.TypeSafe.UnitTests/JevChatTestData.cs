// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Builds TypeSafe API responses and questions for the chat client tests.
/// </summary>
internal static class JevChatTestData
{
    public const string Route = "__af_tool__.route";

    /// <summary>Two questions about a support ticket: a Choice and a Noul.</summary>
    public static Dictionary<string, JevQuestion> Questions() => new()
    {
        ["department"] = new JevChoiceQuestion
        {
            Instructions = "Which team should handle the request?",
            Criteria = new Dictionary<string, JevEntry> { ["billing"] = "Payments or refunds", ["technical"] = "Bugs or integrations" },
        },
        ["is_urgent"] = new JevNoulQuestion { Instructions = "Does the request need urgent attention?" },
    };

    /// <summary>The answers to <see cref="Questions"/>.</summary>
    public static string[] UserAnswers(string department = "technical") =>
        [Choice("department", department, "billing", "technical"), Noul("is_urgent", 0.9)];

    public static string Result(params string[] answers) =>
        "{\"model\":\"jev-test\",\"answers\":{" + string.Join(",", answers) + "},\"usage\":{\"input_tokens\":10,\"output_tokens\":2}}";

    public static string Result(IEnumerable<string> answers, params string[] more) => Result([.. answers, .. more]);

    public static string Choice(string id, string choice, params string[] labels)
    {
        string probabilities = string.Join(",", labels.Select(label => $"\"{label}\":{(label == choice ? "1.0" : "0.0")}"));
        return $"\"{id}\":{{\"type\":\"choice\",\"choice\":\"{choice}\",\"confidence\":0.9,\"probabilities\":{{{probabilities}}}}}";
    }

    public static string Noul(string id, double noul) =>
        $"\"{id}\":{{\"type\":\"noul\",\"noul\":{noul.ToString(CultureInfo.InvariantCulture)}}}";

    public static string Score(string id, double score, int levels)
    {
        string legend = string.Join(",", Enumerable.Range(0, levels).Select(level => $"\"{level}\":\"Level {level}\""));
        string probabilities = string.Join(",", Enumerable.Range(0, levels).Select(level => $"\"{level}\":{(level == (int)score ? "1.0" : "0.0")}"));
        return $"\"{id}\":{{\"type\":\"score\",\"score\":{score.ToString(CultureInfo.InvariantCulture)},\"confidence\":0.8,\"legend\":{{{legend}}},\"probabilities\":{{{probabilities}}}}}";
    }

    /// <summary>A route answer that selects one of the route labels.</summary>
    public static string RouteTo(string label, params string[] labels) => Choice(Route, label, labels);
}
