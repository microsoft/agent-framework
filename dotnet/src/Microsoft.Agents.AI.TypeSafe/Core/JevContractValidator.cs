// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Checks requests before they are sent and results before they are returned to the caller.
/// </summary>
/// <remarks>
/// <para>
/// Request rules follow the official TypeSafe SDK (at least one question; a Score rubric of at least two entries) and
/// the limits the API rejects (at most 255 Choice alternatives and 10 Score entries; a Noul needs instructions or
/// criteria; the state and Score rubric entries may not be null, although the SDK types allow it). Checking them here
/// saves a round trip and gives the model a message that says what to fix.
/// </para>
/// <para>
/// Requests come from a model, so their errors are <see cref="ArgumentException"/>. Results come from the API or from
/// a custom mapping, so their errors are <see cref="InvalidOperationException"/>; they point at a mapping bug, not at
/// the model.
/// </para>
/// </remarks>
internal static class JevContractValidator
{
    public const int MaxChoiceCriteria = 255;
    public const int MinScoreCriteria = 2;
    public const int MaxScoreCriteria = 10;

    // Jev computes scores and probabilities in floating point, so values may exceed their bounds by rounding error.
    private const double Tolerance = 1e-6;

    public static void ValidateRequest(JevRequest request)
    {
        // The SDK types allow a null state, but the API answers 422 ("Field required").
        if (request.State.IsNull)
        {
            Throw.ArgumentException(nameof(request), "The state must be text or a JSON object or array.");
        }

        if (request.Questions is null || request.Questions.Count == 0)
        {
            Throw.ArgumentException(nameof(request), "At least one question is required.");
        }

        foreach (KeyValuePair<string, JevQuestion> entry in request.Questions)
        {
            string id = entry.Key;
            switch (entry.Value)
            {
                case null:
                    Throw.ArgumentException(nameof(request), $"Question '{id}' is null.");
                    break;

                case JevChoiceQuestion choice:
                    int alternatives = choice.Criteria?.Count ?? 0;
                    if (alternatives is < 1 or > MaxChoiceCriteria)
                    {
                        Throw.ArgumentException(nameof(request), $"Choice question '{id}' has {Count(alternatives, "alternative")}; it needs from 1 to {MaxChoiceCriteria}.");
                    }

                    break;

                case JevScoreQuestion score:
                    int scores = score.Criteria?.Count ?? 0;
                    if (scores is < MinScoreCriteria or > MaxScoreCriteria)
                    {
                        Throw.ArgumentException(nameof(request), $"Score question '{id}' has {Count(scores, "criterion", "criteria")}; it needs from {MinScoreCriteria} to {MaxScoreCriteria}.");
                    }

                    // The SDK types allow null rubric entries, but the API answers 422 for them.
                    for (int index = 0; index < scores; index++)
                    {
                        if (score.Criteria![index].IsNull)
                        {
                            Throw.ArgumentException(nameof(request), $"Score question '{id}' has a null criterion at index {index.ToString(CultureInfo.InvariantCulture)}; every score needs text or JSON.");
                        }
                    }

                    break;

                case JevNoulQuestion noul:
                    if (IsEmpty(noul.Instructions) && IsEmpty(noul.Criteria?.True) && IsEmpty(noul.Criteria?.False))
                    {
                        Throw.ArgumentException(nameof(request), $"Noul question '{id}' needs instructions or criteria.");
                    }

                    break;
            }
        }
    }

    public static void ValidateResult(JevRequest request, JevResult result)
    {
        if (result.Answers is null)
        {
            Throw.InvalidOperationException("The Jev result has no answers.");
        }

        foreach (KeyValuePair<string, JevQuestion> entry in request.Questions)
        {
            string id = entry.Key;
            if (!result.Answers.TryGetValue(id, out JevResponse? answer) || answer is null)
            {
                Throw.InvalidOperationException($"The Jev result has no answer for question '{id}'.");
            }

            switch (entry.Value, answer)
            {
                case (JevChoiceQuestion question, JevChoiceResponse choice):
                    // A label outside the criteria would reach the model as a value it never offered, which is how a
                    // mapping that converts between labels and a client's own values would fail silently.
                    if (choice.Choice is null || !question.Criteria.ContainsKey(choice.Choice))
                    {
                        Throw.InvalidOperationException($"The answer to question '{id}' chose '{choice.Choice}', which is not one of its labels.");
                    }

                    EnsureInRange(choice.Confidence, 0, 1, id, "confidence");
                    EnsureProbabilities(choice.Probabilities, id, key => question.Criteria.ContainsKey(key), "one of its labels");
                    break;

                case (JevScoreQuestion question, JevScoreResponse score):
                    EnsureInRange(score.Score, 0, question.Criteria.Count - 1, id, "score");
                    EnsureInRange(score.Confidence, 0, 1, id, "confidence");

                    // Score responses key their probabilities and legend by score ("0", "1", ...).
                    int scores = question.Criteria.Count;
                    bool IsScore(string key) => int.TryParse(key, NumberStyles.None, CultureInfo.InvariantCulture, out int value) && value < scores;
                    string scoreRange = $"a score from 0 to {(scores - 1).ToString(CultureInfo.InvariantCulture)}";
                    EnsureProbabilities(score.Probabilities, id, IsScore, scoreRange);
                    EnsureKeys(score.Legend?.Keys, id, "legend", IsScore, scoreRange);
                    break;

                case (JevNoulQuestion, JevNoulResponse noul):
                    EnsureInRange(noul.Noul, 0, 1, id, "noul");
                    break;

                default:
                    Throw.InvalidOperationException($"The answer to question '{id}' is a {KindOf(answer)} answer, but the question is a {KindOf(entry.Value)} question.");
                    break;
            }
        }
    }

    private static bool IsEmpty(JevEntry? entry) =>
        entry is not { } value || value.IsNull || (value.Kind == JsonValueKind.String && string.IsNullOrWhiteSpace(value.Text));

    /// <summary>
    /// Checks that every probability is in range and is keyed by something the question offered. A mapping that fills
    /// probabilities with a client's own labels would otherwise show the model alternatives it never asked about.
    /// </summary>
    private static void EnsureProbabilities(IReadOnlyDictionary<string, double>? probabilities, string id, Func<string, bool> isValidKey, string expected)
    {
        if (probabilities is null)
        {
            Throw.InvalidOperationException($"The answer to question '{id}' has no probabilities.");
        }

        EnsureKeys(probabilities.Keys, id, "probabilities", isValidKey, expected);
        foreach (KeyValuePair<string, double> probability in probabilities)
        {
            EnsureInRange(probability.Value, 0, 1, id, $"probability '{probability.Key}'");
        }
    }

    private static void EnsureKeys(IEnumerable<string>? keys, string id, string field, Func<string, bool> isValidKey, string expected)
    {
        foreach (string key in keys ?? [])
        {
            if (!isValidKey(key))
            {
                Throw.InvalidOperationException($"The answer to question '{id}' has {field} for '{key}', which is not {expected}.");
            }
        }
    }

    private static void EnsureInRange(double value, double min, double max, string id, string field)
    {
        // NaN and infinity fail these comparisons too; they cannot be written as JSON at all.
        if (!(value >= min - Tolerance && value <= max + Tolerance))
        {
            Throw.InvalidOperationException(string.Format(
                CultureInfo.InvariantCulture,
                "The answer to question '{0}' has {1} {2}, which is outside the range {3} to {4}.",
                id,
                field,
                value,
                min,
                max));
        }
    }

    private static string Count(int count, string singular, string? plural = null) =>
        count == 1 ? $"1 {singular}" : $"{count.ToString(CultureInfo.InvariantCulture)} {plural ?? singular + "s"}";

    private static string KindOf(object value) =>
        value switch
        {
            JevChoiceQuestion or JevChoiceResponse => "Choice",
            JevScoreQuestion or JevScoreResponse => "Score",
            JevNoulQuestion or JevNoulResponse => "Noul",
            _ => value.GetType().Name,
        };
}
