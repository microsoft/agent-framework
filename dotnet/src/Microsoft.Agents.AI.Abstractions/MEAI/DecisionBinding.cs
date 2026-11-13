// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // File may only contain a single type — binding proof types are co-located as one API surface.
#pragma warning disable SA1649 // File name should match first type name — binding proof types are co-located as one API surface.
#pragma warning disable SA1204 // Static extension type is intentionally grouped with the binding types.

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>Provides an explicit mapping from a choice candidate ID to an enum value.</summary>
/// <typeparam name="TEnum">The application-owned enum type.</typeparam>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionEnumDefinition<TEnum>
    where TEnum : struct, Enum
{
    private readonly ReadOnlyDictionary<string, TEnum> _values;

    /// <summary>Initializes a new instance of the <see cref="DecisionEnumDefinition{TEnum}"/> class.</summary>
    public DecisionEnumDefinition(IEnumerable<DecisionEnumValue<TEnum>> values)
    {
        _ = Throw.IfNull(values);

        DecisionEnumValue<TEnum>[] copy = values.ToArray();
        if (copy.Length == 0)
        {
            Throw.ArgumentException(nameof(values), "An enum definition requires at least one value.");
        }

        Dictionary<string, TEnum> byId = new(StringComparer.Ordinal);
        HashSet<TEnum> enumValues = new();
        DecisionCandidate[] candidates = new DecisionCandidate[copy.Length];

        for (int i = 0; i < copy.Length; i++)
        {
            DecisionEnumValue<TEnum> value = copy[i];
            if (!enumValues.Add(value.Value))
            {
                Throw.ArgumentException(nameof(values), "Enum aliases or duplicate enum values are not allowed.");
            }

            if (byId.ContainsKey(value.Id))
            {
                Throw.ArgumentException(
                    nameof(values),
                    "Enum candidate IDs must be unique using ordinal comparison.");
            }

            byId.Add(value.Id, value.Value);
            candidates[i] = new DecisionCandidate(value.Id, value.Description);
        }

        _values = new ReadOnlyDictionary<string, TEnum>(byId);
        Candidates = Array.AsReadOnly(candidates);
    }

    /// <summary>Gets the ordered candidate snapshot for a choice question.</summary>
    public IReadOnlyList<DecisionCandidate> Candidates { get; }

    /// <summary>Creates a choice question using this exact enum mapping.</summary>
    /// <returns>The choice question with the exact mapped candidate IDs.</returns>
    public ChoiceDecisionQuestion CreateQuestion(string id, string? instructions) =>
        new(id, instructions, Candidates);

    /// <summary>Maps an exact selected candidate ID to its enum value.</summary>
    /// <returns>The mapped enum value.</returns>
    public TEnum Parse(string candidateId)
    {
        _ = Throw.IfNullOrWhitespace(candidateId);
        if (_values.TryGetValue(candidateId, out TEnum value))
        {
            return value;
        }

        throw new DecisionProtocolException($"Unknown candidate ID '{candidateId}'.");
    }
}

/// <summary>Describes one enum mapping entry.</summary>
/// <typeparam name="TEnum">The application-owned enum type.</typeparam>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionEnumValue<TEnum>
    where TEnum : struct, Enum
{
    /// <summary>Initializes a new instance of the <see cref="DecisionEnumValue{TEnum}"/> class.</summary>
    public DecisionEnumValue(TEnum value, string id, string description)
    {
        Value = value;
        Id = Throw.IfNullOrWhitespace(id);
        Description = Throw.IfNullOrWhitespace(description);
    }

    /// <summary>Gets the application enum value.</summary>
    public TEnum Value { get; }

    /// <summary>Gets the exact candidate ID.</summary>
    public string Id { get; }

    /// <summary>Gets the candidate description.</summary>
    public string Description { get; }
}

/// <summary>Provides typed access to a complete decision response.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionAnswerSet
{
    internal DecisionAnswerSet(DecisionResponse response)
    {
        Response = response;
    }

    /// <summary>Gets the complete unmodified response, including probability evidence.</summary>
    public DecisionResponse Response { get; }

    /// <summary>Gets a binary answer by exact question ID.</summary>
    /// <returns>The complete binary answer.</returns>
    public BinaryDecisionAnswer GetBinary(string questionId) =>
        Response.GetAnswer(questionId) as BinaryDecisionAnswer ??
        throw new DecisionProtocolException($"Question '{questionId}' is not binary.");

    /// <summary>Gets a choice answer by exact question ID.</summary>
    /// <returns>The complete choice answer.</returns>
    public ChoiceDecisionAnswer GetChoice(string questionId) =>
        Response.GetAnswer(questionId) as ChoiceDecisionAnswer ??
        throw new DecisionProtocolException($"Question '{questionId}' is not a choice.");

    /// <summary>Gets a choice answer and maps its exact selected ID to an enum.</summary>
    /// <typeparam name="TEnum">The application-owned enum type.</typeparam>
    /// <returns>The mapped enum value.</returns>
    public TEnum GetChoice<TEnum>(string questionId, DecisionEnumDefinition<TEnum> definition)
        where TEnum : struct, Enum
    {
        _ = Throw.IfNull(definition);
        return definition.Parse(GetChoice(questionId).SelectedCandidateId);
    }

    /// <summary>Gets a score answer by exact question ID.</summary>
    /// <returns>The complete score answer.</returns>
    public ScoreDecisionAnswer GetScore(string questionId) =>
        Response.GetAnswer(questionId) as ScoreDecisionAnswer ??
        throw new DecisionProtocolException($"Question '{questionId}' is not a score.");
}

/// <summary>Maps one complete response to an application-owned result without inference or reflection.</summary>
/// <typeparam name="TResult">The application-owned result type.</typeparam>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionResultBinding<TResult>
{
    private readonly Func<DecisionAnswerSet, TResult> _map;

    /// <summary>Initializes a new instance of the <see cref="DecisionResultBinding{TResult}"/> class.</summary>
    /// <param name="resultTypeInfo">The source-generated JSON contract for the application result.</param>
    /// <param name="map">The application-owned mapping delegate.</param>
    public DecisionResultBinding(
        JsonTypeInfo<TResult> resultTypeInfo,
        Func<DecisionAnswerSet, TResult> map)
    {
        ResultTypeInfo = Throw.IfNull(resultTypeInfo);
        _map = Throw.IfNull(map);
    }

    /// <summary>Gets the explicit source-generated result contract.</summary>
    public JsonTypeInfo<TResult> ResultTypeInfo { get; }

    internal TResult Map(DecisionResponse response) => _map(new DecisionAnswerSet(response));
}

/// <summary>Provides response binding extensions.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public static class DecisionBindingExtensions
{
    /// <summary>Maps a complete response locally using the supplied explicit binding.</summary>
    /// <typeparam name="TResult">The application-owned result type.</typeparam>
    /// <returns>The application-owned result.</returns>
    public static TResult Bind<TResult>(
        this DecisionResponse response,
        DecisionResultBinding<TResult> binding)
    {
        _ = Throw.IfNull(response);
        _ = Throw.IfNull(binding);
        return binding.Map(response);
    }
}
