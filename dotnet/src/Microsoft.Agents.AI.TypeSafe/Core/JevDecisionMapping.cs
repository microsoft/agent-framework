// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Converts between the Jev contract types and the provider-neutral decision types.
/// </summary>
/// <remarks>
/// <para>
/// A Binary question is a Noul, a Choice question a Choice whose labels are the candidate IDs, and a Score question a
/// Score whose rubric is the level descriptions in order. Jev keys Score probabilities by level index, so answers are
/// mapped back to the level IDs by position.
/// </para>
/// <para>
/// The decision types require complete, correlated answers: every candidate and level needs a probability, and each
/// distribution must sum to 1. Jev computes its values in floating point, so a value that exceeds its bounds by less
/// than <see cref="Tolerance"/> is moved onto the bound, as <see cref="JevContractValidator"/> already accepts it.
/// Nothing else is repaired.
/// </para>
/// </remarks>
internal static class JevDecisionMapping
{
    /// <summary>
    /// Gets the precision of Jev probabilities. Jev does not declare a rounding, so they are taken at face value.
    /// </summary>
    public const DecisionPrecision Precision = DecisionPrecision.HighPrecision;

    /// <summary>The name of the <see cref="DecisionAnswer.AdditionalProperties"/> entry that holds Jev's confidence.</summary>
    public const string ConfidenceProperty = "confidence";

    private const double Tolerance = 1e-6;

    /// <summary>Converts a decision state into a Jev state, which is text or a JSON object or array.</summary>
    public static JevEntry ToEntry(JsonElement state)
    {
        if (state.ValueKind is not (JsonValueKind.String or JsonValueKind.Object or JsonValueKind.Array))
        {
            Throw.ArgumentException(nameof(state), $"Jev answers questions about text or a JSON object or array, but the state is a JSON {state.ValueKind}.");
        }

        return new JevEntry(state);
    }

    /// <summary>Converts a decision question into the Jev question that asks it.</summary>
    public static JevQuestion ToJevQuestion(DecisionQuestion question) =>
        question switch
        {
            BinaryDecisionQuestion binary => new JevNoulQuestion
            {
                Instructions = ToEntry(binary.Instructions),
                Criteria = binary.TrueDescription is null && binary.FalseDescription is null
                    ? null
                    : new JevNoulCriteria { True = ToEntry(binary.TrueDescription), False = ToEntry(binary.FalseDescription) },
            },
            ChoiceDecisionQuestion choice => new JevChoiceQuestion
            {
                Instructions = ToEntry(choice.Instructions),
                Criteria = ToCriteria(choice.Candidates),
            },
            ScoreDecisionQuestion score => new JevScoreQuestion
            {
                Instructions = ToEntry(score.Instructions),
                Criteria = [.. score.Levels.Select(level => (JevEntry)level.Description)],
            },
            _ => throw new NotSupportedException($"Jev does not answer {question.Kind} questions."),
        };

    /// <summary>
    /// Converts a Jev question into the decision question that correlates its answer.
    /// </summary>
    /// <remarks>
    /// JSON instructions and criteria become their JSON text, and an undescribed Choice label is described by the
    /// label itself. The Jev question itself is what is sent (see <see cref="JevDecisionRequestOptions"/>), so these
    /// texts never reach the API. Call <see cref="JevContractValidator.ValidateQuestions"/> first, so that invalid
    /// questions fail with the Jev rule they break.
    /// </remarks>
    public static DecisionQuestion ToDecisionQuestion(string id, JevQuestion question) =>
        question switch
        {
            JevNoulQuestion noul => ToBinaryQuestion(id, noul),
            JevChoiceQuestion choice => new ChoiceDecisionQuestion(
                id,
                ToText(choice.Instructions),
                [.. choice.Criteria.Select(criterion => new DecisionCandidate(criterion.Key, ToText(criterion.Value) ?? criterion.Key))]),
            JevScoreQuestion score => new ScoreDecisionQuestion(
                id,
                ToText(score.Instructions),
                [.. score.Criteria.Select((criterion, index) => new DecisionScoreLevel(ToKey(index), ToText(criterion) ?? ToKey(index)))]),
            _ => throw new ArgumentException($"Question '{id}' is not a Jev Choice, Score, or Noul question.", nameof(question)),
        };

    /// <summary>
    /// Converts Jev's answer to a question into the decision answer.
    /// </summary>
    /// <exception cref="DecisionProtocolException">The answer is not a complete answer to the question.</exception>
    public static DecisionAnswer ToDecisionAnswer(DecisionQuestion question, JevResponse response) =>
        (question, response) switch
        {
            (BinaryDecisionQuestion, JevNoulResponse noul) => new BinaryDecisionAnswer(
                question.Id,
                OntoBounds(noul.Noul, 1),
                Precision,
                rawRepresentation: noul),
            (ChoiceDecisionQuestion choice, JevChoiceResponse answer) => new ChoiceDecisionAnswer(
                question.Id,
                answer.Choice,
                [.. choice.Candidates.Select(candidate => new DecisionProbability(candidate.Id, GetProbability(answer.Probabilities, candidate.Id, question.Id)))],
                Precision,
                rawRepresentation: answer,
                additionalProperties: Confidence(answer.Confidence)),
            (ScoreDecisionQuestion score, JevScoreResponse answer) => new ScoreDecisionAnswer(
                question.Id,
                OntoBounds(answer.Score, score.Levels.Count - 1),
                [.. score.Levels.Select((level, index) => new DecisionProbability(level.Id, GetProbability(answer.Probabilities, ToKey(index), question.Id)))],
                Precision,
                rawRepresentation: answer,
                additionalProperties: Confidence(answer.Confidence)),
            _ => throw new DecisionProtocolException($"The Jev answer to question '{question.Id}' does not match its {question.Kind} question."),
        };

    /// <summary>Converts Jev token usage into usage details.</summary>
    public static UsageDetails? ToUsage(JevUsage? usage) =>
        usage is { } tokens
            ? new UsageDetails { InputTokenCount = tokens.InputTokens, OutputTokenCount = tokens.OutputTokens, TotalTokenCount = tokens.InputTokens + tokens.OutputTokens }
            : null;

    /// <summary>
    /// Gets the Jev result of a decision response from <see cref="JevDecisionClient"/>, with only the answers that the
    /// response holds.
    /// </summary>
    public static JevResult ToJevResult(DecisionResponse response)
    {
        if (response.RawRepresentation is not JevResult result)
        {
            throw new InvalidOperationException("The decision response does not come from Jev.");
        }

        var answers = new Dictionary<string, JevResponse>(response.Answers.Count, StringComparer.Ordinal);
        foreach (DecisionAnswer answer in response.Answers)
        {
            answers[answer.QuestionId] = result.Answers[answer.QuestionId];
        }

        return new JevResult { Model = result.Model, Answers = answers, Usage = result.Usage };
    }

    private static BinaryDecisionQuestion ToBinaryQuestion(string id, JevNoulQuestion noul)
    {
        string? instructions = ToText(noul.Instructions);
        string? trueDescription = ToText(noul.Criteria?.True);
        string? falseDescription = ToText(noul.Criteria?.False);

        // A Noul may describe only one outcome, but a Binary question needs instructions or both descriptions, so the
        // one description also stands in for the instructions.
        return new BinaryDecisionQuestion(
            id,
            instructions ?? (trueDescription is null || falseDescription is null ? trueDescription ?? falseDescription : null),
            trueDescription,
            falseDescription);
    }

    private static Dictionary<string, JevEntry> ToCriteria(IReadOnlyList<DecisionCandidate> candidates)
    {
        var criteria = new Dictionary<string, JevEntry>(candidates.Count, StringComparer.Ordinal);
        foreach (DecisionCandidate candidate in candidates)
        {
            criteria[candidate.Id] = candidate.Description;
        }

        return criteria;
    }

    private static JevEntry? ToEntry(string? text)
    {
        // A null string converts to JevEntry.Null, which is written as JSON null, so an absent text stays absent.
        if (string.IsNullOrEmpty(text))
        {
            return null;
        }

        return JevEntry.FromString(text);
    }

    private static string? ToText(JevEntry? entry) =>
        entry is { IsNull: false } value && value.ToString() is { } text && !string.IsNullOrWhiteSpace(text) ? text : null;

    private static string ToKey(int index) => index.ToString(CultureInfo.InvariantCulture);

    private static double GetProbability(IReadOnlyDictionary<string, double> probabilities, string key, string questionId) =>
        probabilities.TryGetValue(key, out double probability)
            ? OntoBounds(probability, 1)
            : throw new DecisionProtocolException($"The Jev answer to question '{questionId}' has no probability for '{key}'.");

    private static double OntoBounds(double value, double maximum) =>
        value < 0 && value >= -Tolerance ? 0
        : value > maximum && value <= maximum + Tolerance ? maximum
        : value;

    private static Dictionary<string, object?> Confidence(double confidence) =>
        new(StringComparer.Ordinal) { [ConfidenceProperty] = confidence };
}
