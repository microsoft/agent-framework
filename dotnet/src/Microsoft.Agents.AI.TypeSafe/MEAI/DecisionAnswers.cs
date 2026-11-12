// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // File may only contain a single type — decision answer types are co-located as one immutable model.
#pragma warning disable SA1649 // File name should match first type name — decision answer types are co-located as one immutable model.
#pragma warning disable CA1032 // Implement standard exception constructors — protocol exceptions expose the protocol-specific constructors.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>Identifies the precision represented by provider-reported probabilities.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public enum DecisionPrecision
{
    /// <summary>The provider reports values without a declared decimal rounding.</summary>
    HighPrecision,

    /// <summary>The provider reports values rounded to four decimal places.</summary>
    FourDecimalPlaces,

    /// <summary>The provider reports values rounded to two decimal places.</summary>
    TwoDecimalPlaces,
}

/// <summary>Represents one named probability observation.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionProbability
{
    /// <summary>Initializes a new instance of the <see cref="DecisionProbability"/> class.</summary>
    /// <param name="id">The exact opaque candidate or level ID.</param>
    /// <param name="value">The probability value.</param>
    [JsonConstructor]
    public DecisionProbability(string id, double value)
    {
        Id = Throw.IfNullOrWhitespace(id);
        Value = value;
    }

    /// <summary>Gets the exact opaque candidate or level ID.</summary>
    public string Id { get; }

    /// <summary>Gets the native double probability value.</summary>
    public double Value { get; }
}

/// <summary>Represents a provider result for one decision question.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(BinaryDecisionAnswer), "binary")]
[JsonDerivedType(typeof(ChoiceDecisionAnswer), "choice")]
[JsonDerivedType(typeof(ScoreDecisionAnswer), "score")]
public abstract class DecisionAnswer
{
    internal const double DistributionTolerance = 1e-6;

    private protected DecisionAnswer(
        string questionId,
        DecisionKind kind,
        DecisionPrecision precision,
        object? rawRepresentation,
        IReadOnlyDictionary<string, object?>? additionalProperties)
    {
        QuestionId = Throw.IfNullOrWhitespace(questionId);
        if (!Enum.IsDefined(typeof(DecisionPrecision), precision))
        {
            Throw.ArgumentOutOfRangeException(nameof(precision));
        }

        Kind = kind;
        Precision = precision;
        RawRepresentation = rawRepresentation;
        AdditionalProperties = DecisionSnapshots.Properties(additionalProperties);
    }

    /// <summary>Gets the exact opaque question ID this answer belongs to.</summary>
    public string QuestionId { get; }

    /// <summary>Gets the semantic kind of this answer.</summary>
    public DecisionKind Kind { get; }

    /// <summary>Gets the precision declared for the numeric observations.</summary>
    public DecisionPrecision Precision { get; }

    /// <summary>
    /// Gets the provider-owned raw representation, if available.
    /// This value is not cloned or used for semantic data and must be treated as diagnostic-only.
    /// </summary>
    [JsonIgnore]
    public object? RawRepresentation { get; }

    /// <summary>
    /// Gets an owned read-only snapshot of provider extension data.
    /// Values are shallow-copied references and must be independently safe to share.
    /// </summary>
    public IReadOnlyDictionary<string, object?>? AdditionalProperties { get; }

    internal static void ValidateProbability(double value)
    {
        if (double.IsNaN(value) || double.IsInfinity(value) || value < 0 || value > 1)
        {
            throw new DecisionProtocolException("Probability must be finite and in the range [0, 1].");
        }
    }

    internal static void ValidateDistribution(
        IReadOnlyList<DecisionProbability> probabilities,
        DecisionPrecision precision)
    {
        double sum = 0;
        HashSet<string> ids = new(StringComparer.Ordinal);

        foreach (DecisionProbability probability in probabilities)
        {
            if (probability is null)
            {
                throw new DecisionProtocolException("A probability distribution cannot contain null entries.");
            }

            if (!ids.Add(probability.Id))
            {
                throw new DecisionProtocolException("A probability distribution contains a duplicate ID.");
            }

            ValidateProbability(probability.Value);
            sum += probability.Value;
        }

        double tolerance = GetDistributionTolerance(precision, probabilities.Count);
        if (Math.Abs(sum - 1) > tolerance)
        {
            throw new DecisionProtocolException(
                "A probability distribution must sum to 1 within the bound allowed by its declared rounding.");
        }

        double roundingHalfUnit = GetRoundingHalfUnit(precision);
        double lowerBound = 0;
        double upperBound = 0;
        foreach (DecisionProbability probability in probabilities)
        {
            lowerBound += Math.Max(0, probability.Value - roundingHalfUnit);
            upperBound += Math.Min(1, probability.Value + roundingHalfUnit);
        }

        if (lowerBound > 1 + DistributionTolerance || upperBound < 1 - DistributionTolerance)
        {
            throw new DecisionProtocolException(
                "A probability distribution has no normalized latent values consistent with its declared rounding.");
        }
    }

    internal static double GetDistributionTolerance(DecisionPrecision precision, int count)
    {
        return precision switch
        {
            DecisionPrecision.HighPrecision => DistributionTolerance,
            DecisionPrecision.FourDecimalPlaces => (count * 0.00005) + DistributionTolerance,
            DecisionPrecision.TwoDecimalPlaces => (count * 0.005) + DistributionTolerance,
            _ => throw new ArgumentOutOfRangeException(nameof(precision)),
        };
    }

    internal static (double Minimum, double Maximum) GetFeasibleExpectedScoreBounds(
        IReadOnlyList<DecisionProbability> probabilities,
        DecisionPrecision precision)
    {
        double roundingHalfUnit = GetRoundingHalfUnit(precision);
        double lowerMass = 0;
        double upperMass = 0;
        for (int i = 0; i < probabilities.Count; i++)
        {
            double probability = probabilities[i].Value;
            lowerMass += Math.Max(0, probability - roundingHalfUnit);
            upperMass += Math.Min(1, probability + roundingHalfUnit);
        }

        if (lowerMass > 1 + DistributionTolerance || upperMass < 1 - DistributionTolerance)
        {
            throw new DecisionProtocolException(
                "A probability distribution has no normalized latent values consistent with its declared rounding.");
        }

        double remaining = Math.Max(0, 1 - lowerMass);
        double minimum = 0;
        for (int i = 0; i < probabilities.Count; i++)
        {
            double lower = Math.Max(0, probabilities[i].Value - roundingHalfUnit);
            double capacity = Math.Min(1, probabilities[i].Value + roundingHalfUnit) - lower;
            double allocated = Math.Min(remaining, capacity);
            minimum += (lower + allocated) * i;
            remaining -= allocated;
        }

        remaining = Math.Max(0, 1 - lowerMass);
        double maximum = 0;
        double[] lowerValues = new double[probabilities.Count];
        for (int i = 0; i < probabilities.Count; i++)
        {
            lowerValues[i] = Math.Max(0, probabilities[i].Value - roundingHalfUnit);
            maximum += lowerValues[i] * i;
        }

        for (int i = probabilities.Count - 1; i >= 0; i--)
        {
            double capacity = Math.Min(1, probabilities[i].Value + roundingHalfUnit) - lowerValues[i];
            double allocated = Math.Min(remaining, capacity);
            maximum += allocated * i;
            remaining -= allocated;
        }

        if (remaining > DistributionTolerance)
        {
            throw new DecisionProtocolException(
                "A probability distribution has no normalized latent values consistent with its declared rounding.");
        }

        return (minimum, maximum);
    }

    internal static double GetRoundingHalfUnit(DecisionPrecision precision) =>
        precision switch
        {
            DecisionPrecision.HighPrecision => 0,
            DecisionPrecision.FourDecimalPlaces => 0.00005,
            DecisionPrecision.TwoDecimalPlaces => 0.005,
            _ => throw new ArgumentOutOfRangeException(nameof(precision)),
        };
}

/// <summary>Represents the probability that a binary proposition is true.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class BinaryDecisionAnswer : DecisionAnswer
{
    /// <summary>Initializes a new instance of the <see cref="BinaryDecisionAnswer"/> class.</summary>
    [JsonConstructor]
    public BinaryDecisionAnswer(
        string questionId,
        double trueProbability,
        DecisionPrecision precision = DecisionPrecision.HighPrecision,
        object? rawRepresentation = null,
        IReadOnlyDictionary<string, object?>? additionalProperties = null)
        : base(questionId, DecisionKind.Binary, precision, rawRepresentation, additionalProperties)
    {
        ValidateProbability(trueProbability);
        TrueProbability = trueProbability;
    }

    /// <summary>Gets the probability that the proposition is true.</summary>
    public double TrueProbability { get; }
}

/// <summary>Represents a selected candidate and its complete probability distribution.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class ChoiceDecisionAnswer : DecisionAnswer
{
    /// <summary>Initializes a new instance of the <see cref="ChoiceDecisionAnswer"/> class.</summary>
    [JsonConstructor]
    public ChoiceDecisionAnswer(
        string questionId,
        string selectedCandidateId,
        IReadOnlyList<DecisionProbability> probabilities,
        DecisionPrecision precision = DecisionPrecision.HighPrecision,
        object? rawRepresentation = null,
        IReadOnlyDictionary<string, object?>? additionalProperties = null)
        : base(questionId, DecisionKind.Choice, precision, rawRepresentation, additionalProperties)
    {
        SelectedCandidateId = Throw.IfNullOrWhitespace(selectedCandidateId);
        _ = Throw.IfNull(probabilities);

        DecisionProbability[] copy = probabilities.ToArray();
        if (copy.Length == 0)
        {
            throw new DecisionProtocolException("A choice answer requires a complete distribution.");
        }

        ValidateDistribution(copy, precision);
        if (!Array.Exists(copy, probability => string.Equals(probability.Id, SelectedCandidateId, StringComparison.Ordinal)))
        {
            throw new DecisionProtocolException("The selected candidate is not present in the distribution.");
        }

        Probabilities = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the exact selected candidate ID.</summary>
    public string SelectedCandidateId { get; }

    /// <summary>Gets the complete ordered candidate distribution.</summary>
    public IReadOnlyList<DecisionProbability> Probabilities { get; }
}

/// <summary>
/// Represents an ordinal score and its complete level distribution.
/// A reported score is checked against normalized latent values within the declared clipped rounding intervals; observed probabilities and the derived expectation are never repaired.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class ScoreDecisionAnswer : DecisionAnswer
{
    /// <summary>Initializes a new instance of the <see cref="ScoreDecisionAnswer"/> class.</summary>
    [JsonConstructor]
    public ScoreDecisionAnswer(
        string questionId,
        double? score,
        IReadOnlyList<DecisionProbability> probabilities,
        DecisionPrecision precision = DecisionPrecision.HighPrecision,
        object? rawRepresentation = null,
        IReadOnlyDictionary<string, object?>? additionalProperties = null)
        : base(questionId, DecisionKind.Score, precision, rawRepresentation, additionalProperties)
    {
        _ = Throw.IfNull(probabilities);

        DecisionProbability[] copy = probabilities.ToArray();
        if (copy.Length < 2)
        {
            throw new DecisionProtocolException("A score answer requires at least two levels.");
        }

        ValidateDistribution(copy, precision);
        if (score is double reportedScore &&
            (double.IsNaN(reportedScore) || double.IsInfinity(reportedScore) || reportedScore < 0 || reportedScore > copy.Length - 1))
        {
            throw new DecisionProtocolException("A score must be finite and within the ordinal level range.");
        }

        double expectedScore = copy.Select((probability, index) => probability.Value * index).Sum();
        if (score is double nativeScore)
        {
            (double minimum, double maximum) = GetFeasibleExpectedScoreBounds(copy, precision);
            double scalarHalfUnit = GetRoundingHalfUnit(precision);
            if (nativeScore + scalarHalfUnit + DistributionTolerance < minimum ||
                nativeScore - scalarHalfUnit - DistributionTolerance > maximum)
            {
                throw new DecisionProtocolException("The score does not agree with its probability distribution.");
            }
        }

        Score = score;
        ExpectedScore = expectedScore;
        Probabilities = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the provider-reported score, retaining any declared rounding, or <see langword="null"/> when it was not reported.</summary>
    public double? Score { get; }

    /// <summary>Gets the score derived from the observed distribution without repairing it, which may fall outside the ordinal level bounds after rounding.</summary>
    public double ExpectedScore { get; }

    /// <summary>Gets the complete ordered level distribution.</summary>
    public IReadOnlyList<DecisionProbability> Probabilities { get; }
}

/// <summary>Represents a protocol-invalid provider result.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionProtocolException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="DecisionProtocolException"/> class.</summary>
    public DecisionProtocolException()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionProtocolException"/> class with a message.</summary>
    public DecisionProtocolException(string message)
        : base(message)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="DecisionProtocolException"/> class with a message and inner exception.</summary>
    public DecisionProtocolException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

internal static class DecisionSnapshots
{
    internal static IReadOnlyDictionary<string, object?>? Properties(
        IReadOnlyDictionary<string, object?>? entries)
    {
        if (entries is null)
        {
            return null;
        }

        Dictionary<string, object?> copy = new(StringComparer.Ordinal);
        foreach (KeyValuePair<string, object?> property in entries)
        {
            if (copy.ContainsKey(property.Key))
            {
                Throw.ArgumentException(nameof(entries), "Extension property names must be unique.");
            }

            copy.Add(property.Key, property.Value);
        }

        return new ReadOnlyDictionary<string, object?>(copy);
    }
}
