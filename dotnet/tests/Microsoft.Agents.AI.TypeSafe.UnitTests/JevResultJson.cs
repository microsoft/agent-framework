// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Globalization;
using System.Linq;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Builds TypeSafe API responses as JSON, one answer at a time.
/// </summary>
internal static class JevResultJson
{
    public static string Result(params string[] answers) =>
        "{\"model\":\"jev-test\",\"answers\":{" + string.Join(",", answers) + "},\"usage\":{\"input_tokens\":10,\"output_tokens\":2}}";

    public static string Choice(string id, string choice, params string[] labels)
    {
        string probabilities = string.Join(",", labels.Select(label => $"\"{label}\":{(label == choice ? "1.0" : "0.0")}"));
        return $"\"{id}\":{{\"type\":\"choice\",\"choice\":\"{choice}\",\"confidence\":0.9,\"probabilities\":{{{probabilities}}}}}";
    }

    public static string Noul(string id, double noul) =>
        $"\"{id}\":{{\"type\":\"noul\",\"noul\":{noul.ToString(CultureInfo.InvariantCulture)}}}";

    /// <summary>
    /// A Score answer whose probabilities agree with the score, which is their expectation: a fractional score splits
    /// the probability between the two levels around it.
    /// </summary>
    public static string Score(string id, double score, int levels)
    {
        string legend = string.Join(",", Enumerable.Range(0, levels).Select(level => $"\"{level}\":\"Level {level}\""));
        int lower = (int)Math.Floor(score);
        double upperShare = score - lower;
        string probabilities = string.Join(",", Enumerable.Range(0, levels).Select(level =>
        {
            double probability = level == lower ? 1 - upperShare : level == lower + 1 ? upperShare : 0;
            return $"\"{level}\":{probability.ToString(CultureInfo.InvariantCulture)}";
        }));
        return $"\"{id}\":{{\"type\":\"score\",\"score\":{score.ToString(CultureInfo.InvariantCulture)},\"confidence\":0.8,\"legend\":{{{legend}}},\"probabilities\":{{{probabilities}}}}}";
    }
}
