// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // File may only contain a single type — feature projection types are co-located as one API surface.
#pragma warning disable SA1649 // File name should match first type name — feature projection types are co-located as one API surface.
#pragma warning disable SA1204 // Static projection type is intentionally grouped with the feature model.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>Identifies the semantic value projected by a feature coordinate.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public enum DecisionFeatureValueKind
{
    /// <summary>The probability that a binary proposition is true.</summary>
    BinaryTrueProbability,

    /// <summary>The probability that a binary proposition is false.</summary>
    BinaryFalseProbability,

    /// <summary>The probability of one choice candidate.</summary>
    ChoiceProbability,

    /// <summary>The probability of one score level.</summary>
    ScoreProbability,

    /// <summary>The provider-reported ordinal score.</summary>
    Score,

    /// <summary>The ordinal score calculated from the complete observed distribution.</summary>
    ExpectedScore,
}

/// <summary>Names one stable semantic coordinate in a feature schema.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionFeatureCoordinate
{
    /// <summary>Initializes a new instance of the <see cref="DecisionFeatureCoordinate"/> class.</summary>
    public DecisionFeatureCoordinate(
        string name,
        string questionId,
        DecisionFeatureValueKind valueKind,
        string? memberId = null)
    {
        Name = Throw.IfNullOrWhitespace(name);
        QuestionId = Throw.IfNullOrWhitespace(questionId);
        if (!Enum.IsDefined(typeof(DecisionFeatureValueKind), valueKind))
        {
            Throw.ArgumentOutOfRangeException(nameof(valueKind));
        }

        ValueKind = valueKind;

        bool requiresMemberId = valueKind is DecisionFeatureValueKind.ChoiceProbability or DecisionFeatureValueKind.ScoreProbability;
        if (requiresMemberId != (memberId is not null))
        {
            Throw.ArgumentException(
                nameof(memberId),
                requiresMemberId ? "This coordinate kind requires a member ID." : "This coordinate kind does not accept a member ID.");
        }

        if (memberId is not null)
        {
            MemberId = Throw.IfNullOrWhitespace(memberId);
        }
    }

    /// <summary>Gets the stable coordinate name.</summary>
    public string Name { get; }

    /// <summary>Gets the exact question ID supplying this coordinate.</summary>
    public string QuestionId { get; }

    /// <summary>Gets the coordinate semantic kind.</summary>
    public DecisionFeatureValueKind ValueKind { get; }

    /// <summary>Gets the exact candidate or level ID, when applicable.</summary>
    public string? MemberId { get; }
}

/// <summary>Identifies a named feature schema and its version.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionFeatureSchema
{
    /// <summary>Initializes a new instance of the <see cref="DecisionFeatureSchema"/> class.</summary>
    public DecisionFeatureSchema(string id, int version, IEnumerable<DecisionFeatureCoordinate> coordinates)
    {
        Id = Throw.IfNullOrWhitespace(id);
        if (version < 1)
        {
            Throw.ArgumentOutOfRangeException(nameof(version));
        }

        _ = Throw.IfNull(coordinates);
        DecisionFeatureCoordinate[] copy = coordinates.ToArray();
        if (copy.Length == 0 || Array.Exists(copy, static coordinate => coordinate is null))
        {
            Throw.ArgumentException(nameof(coordinates), "Coordinates must be nonempty.");
        }

        HashSet<string> names = new(StringComparer.Ordinal);
        foreach (DecisionFeatureCoordinate coordinate in copy)
        {
            if (!names.Add(coordinate.Name))
            {
                Throw.ArgumentException(nameof(coordinates), "Feature names must be unique using ordinal comparison.");
            }
        }

        Version = version;
        Coordinates = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the stable schema identity.</summary>
    public string Id { get; }

    /// <summary>Gets the schema version.</summary>
    public int Version { get; }

    /// <summary>Gets the ordered coordinate snapshot.</summary>
    public IReadOnlyList<DecisionFeatureCoordinate> Coordinates { get; }
}

/// <summary>Represents one named native-double feature value.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionFeatureValue
{
    /// <summary>Initializes a new instance of the <see cref="DecisionFeatureValue"/> class.</summary>
    public DecisionFeatureValue(string name, double value)
    {
        Name = Throw.IfNullOrWhitespace(name);
        if (double.IsNaN(value) || double.IsInfinity(value))
        {
            Throw.ArgumentOutOfRangeException(nameof(value));
        }

        Value = value;
    }

    /// <summary>Gets the stable coordinate name.</summary>
    public string Name { get; }

    /// <summary>Gets the native double value.</summary>
    public double Value { get; }
}

/// <summary>Represents a named feature projection with schema and provenance.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionFeatureVector
{
    internal DecisionFeatureVector(
        DecisionFeatureSchema schema,
        IEnumerable<DecisionFeatureValue> values,
        DecisionProvenance? provenance)
    {
        Schema = schema;
        Values = Array.AsReadOnly(values.ToArray());
        Provenance = provenance;
    }

    /// <summary>Gets the explicit feature schema.</summary>
    public DecisionFeatureSchema Schema { get; }

    /// <summary>Gets named values in schema order.</summary>
    public IReadOnlyList<DecisionFeatureValue> Values { get; }

    /// <summary>Gets provider/model provenance, when reported by the response.</summary>
    public DecisionProvenance? Provenance { get; }
}

/// <summary>Projects complete decision observations into named native-double coordinates.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public static class DecisionFeatureProjection
{
    /// <summary>Projects a response without an inference call or probability repair.</summary>
    /// <returns>The named feature vector projected from the complete response.</returns>
    public static DecisionFeatureVector Project(
        DecisionResponse response,
        DecisionFeatureSchema schema)
    {
        _ = Throw.IfNull(response);
        _ = Throw.IfNull(schema);

        List<DecisionFeatureValue> values = new(schema.Coordinates.Count);
        foreach (DecisionFeatureCoordinate coordinate in schema.Coordinates)
        {
            DecisionAnswer answer = response.GetAnswer(coordinate.QuestionId);
            double value = coordinate.ValueKind switch
            {
                DecisionFeatureValueKind.BinaryTrueProbability =>
                    GetBinary(answer, coordinate).TrueProbability,
                DecisionFeatureValueKind.BinaryFalseProbability =>
                    1 - GetBinary(answer, coordinate).TrueProbability,
                DecisionFeatureValueKind.ChoiceProbability =>
                    GetProbability(GetChoice(answer, coordinate).Probabilities, coordinate.MemberId!),
                DecisionFeatureValueKind.ScoreProbability =>
                    GetProbability(GetScore(answer, coordinate).Probabilities, coordinate.MemberId!),
                DecisionFeatureValueKind.Score =>
                    GetScore(answer, coordinate).Score ??
                    throw new DecisionProtocolException(
                        $"Question '{coordinate.QuestionId}' does not contain a provider-reported score."),
                DecisionFeatureValueKind.ExpectedScore =>
                    GetScore(answer, coordinate).ExpectedScore,
                _ => throw new ArgumentOutOfRangeException(nameof(schema)),
            };

            values.Add(new DecisionFeatureValue(coordinate.Name, value));
        }

        return new DecisionFeatureVector(schema, values, response.Provenance);
    }

    private static BinaryDecisionAnswer GetBinary(DecisionAnswer answer, DecisionFeatureCoordinate coordinate) =>
        answer as BinaryDecisionAnswer ??
        throw new ArgumentException($"Question '{coordinate.QuestionId}' is not binary.", nameof(coordinate));

    private static ChoiceDecisionAnswer GetChoice(DecisionAnswer answer, DecisionFeatureCoordinate coordinate) =>
        answer as ChoiceDecisionAnswer ??
        throw new ArgumentException($"Question '{coordinate.QuestionId}' is not a choice.", nameof(coordinate));

    private static ScoreDecisionAnswer GetScore(DecisionAnswer answer, DecisionFeatureCoordinate coordinate) =>
        answer as ScoreDecisionAnswer ??
        throw new ArgumentException($"Question '{coordinate.QuestionId}' is not a score.", nameof(coordinate));

    private static double GetProbability(IReadOnlyList<DecisionProbability> probabilities, string memberId)
    {
        foreach (DecisionProbability probability in probabilities)
        {
            if (string.Equals(probability.Id, memberId, StringComparison.Ordinal))
            {
                return probability.Value;
            }
        }

        throw new DecisionProtocolException($"Unknown feature member ID '{memberId}'.");
    }
}
