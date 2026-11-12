// Licensed to the .NET Foundation under one or more agreements.
// The .NET Foundation licenses this file to you under the MIT license.

#pragma warning disable SA1402 // File may only contain a single type — decision question types are co-located as one immutable model.
#pragma warning disable SA1649 // File name should match first type name — decision question types are co-located as one immutable model.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>Identifies the semantic kind of a decision question or answer.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public enum DecisionKind
{
    /// <summary>A two-outcome proposition.</summary>
    Binary,

    /// <summary>A choice from a caller-defined unordered set.</summary>
    Choice,

    /// <summary>A position on a caller-defined ordered scale.</summary>
    Score,
}

/// <summary>Describes a decision question.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(BinaryDecisionQuestion), "binary")]
[JsonDerivedType(typeof(ChoiceDecisionQuestion), "choice")]
[JsonDerivedType(typeof(ScoreDecisionQuestion), "score")]
public abstract class DecisionQuestion
{
    private protected DecisionQuestion(string id, DecisionKind kind, string? instructions)
    {
        Id = Throw.IfNullOrWhitespace(id);
        Kind = kind;
        Instructions = instructions ?? string.Empty;
    }

    /// <summary>Gets the opaque, caller-owned correlation ID for this question.</summary>
    public string Id { get; }

    /// <summary>Gets the semantic kind of this question.</summary>
    public DecisionKind Kind { get; }

    /// <summary>Gets the explicit instructions that define the question.</summary>
    public string Instructions { get; }
}

/// <summary>Describes a binary decision question.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class BinaryDecisionQuestion : DecisionQuestion
{
    /// <summary>Initializes a new instance of the <see cref="BinaryDecisionQuestion"/> class.</summary>
    /// <param name="id">The opaque, caller-owned question ID.</param>
    /// <param name="instructions">The instructions defining the proposition.</param>
    /// <param name="trueDescription">Optional criteria describing a true result.</param>
    /// <param name="falseDescription">Optional criteria describing a false result.</param>
    [JsonConstructor]
    public BinaryDecisionQuestion(
        string id,
        string? instructions = null,
        string? trueDescription = null,
        string? falseDescription = null)
        : base(id, DecisionKind.Binary, instructions)
    {
        if (string.IsNullOrWhiteSpace(instructions) &&
            (string.IsNullOrWhiteSpace(trueDescription) || string.IsNullOrWhiteSpace(falseDescription)))
        {
            Throw.ArgumentException(
                nameof(instructions),
                "Binary questions require instructions or both true and false descriptions.");
        }

        if (trueDescription is not null)
        {
            _ = Throw.IfNullOrWhitespace(trueDescription);
        }

        if (falseDescription is not null)
        {
            _ = Throw.IfNullOrWhitespace(falseDescription);
        }

        TrueDescription = trueDescription;
        FalseDescription = falseDescription;
    }

    /// <summary>Gets the optional criteria describing a true result.</summary>
    public string? TrueDescription { get; }

    /// <summary>Gets the optional criteria describing a false result.</summary>
    public string? FalseDescription { get; }
}

/// <summary>Describes one caller-defined choice candidate.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionCandidate
{
    /// <summary>Initializes a new instance of the <see cref="DecisionCandidate"/> class.</summary>
    /// <param name="id">The exact opaque candidate ID to round-trip in results.</param>
    /// <param name="description">The human-readable candidate criteria.</param>
    [JsonConstructor]
    public DecisionCandidate(string id, string description)
    {
        Id = Throw.IfNullOrWhitespace(id);
        Description = Throw.IfNullOrWhitespace(description);
    }

    /// <summary>Gets the exact opaque, caller-owned candidate ID.</summary>
    public string Id { get; }

    /// <summary>Gets the human-readable candidate criteria.</summary>
    public string Description { get; }
}

/// <summary>Describes a choice decision question.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class ChoiceDecisionQuestion : DecisionQuestion
{
    /// <summary>Initializes a new instance of the <see cref="ChoiceDecisionQuestion"/> class.</summary>
    /// <param name="id">The opaque, caller-owned question ID.</param>
    /// <param name="instructions">The instructions defining the choice.</param>
    /// <param name="candidates">The ordered, caller-defined candidates.</param>
    [JsonConstructor]
    public ChoiceDecisionQuestion(string id, string? instructions, IReadOnlyList<DecisionCandidate> candidates)
        : base(id, DecisionKind.Choice, instructions)
    {
        _ = Throw.IfNull(candidates);

        DecisionCandidate[] copy = candidates.ToArray();
        if (copy.Length == 0 || Array.Exists(copy, static candidate => candidate is null))
        {
            Throw.ArgumentException(nameof(candidates), "Candidates must be nonempty.");
        }

        HashSet<string> ids = new(StringComparer.Ordinal);
        foreach (DecisionCandidate candidate in copy)
        {
            if (!ids.Add(candidate.Id))
            {
                Throw.ArgumentException(
                    nameof(candidates),
                    "Candidate IDs must be unique using ordinal comparison.");
            }
        }

        Candidates = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the ordered, owned candidate snapshot.</summary>
    public IReadOnlyList<DecisionCandidate> Candidates { get; }
}

/// <summary>Describes one level in an ordered score rubric.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionScoreLevel
{
    /// <summary>Initializes a new instance of the <see cref="DecisionScoreLevel"/> class.</summary>
    /// <param name="id">The exact opaque, caller-owned level ID.</param>
    /// <param name="description">The criteria for this level.</param>
    [JsonConstructor]
    public DecisionScoreLevel(string id, string description)
    {
        Id = Throw.IfNullOrWhitespace(id);
        Description = Throw.IfNullOrWhitespace(description);
    }

    /// <summary>Gets the exact opaque level ID.</summary>
    public string Id { get; }

    /// <summary>Gets the criteria for this level.</summary>
    public string Description { get; }
}

/// <summary>Describes a score decision question.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class ScoreDecisionQuestion : DecisionQuestion
{
    /// <summary>Initializes a new instance of the <see cref="ScoreDecisionQuestion"/> class.</summary>
    /// <param name="id">The opaque, caller-owned question ID.</param>
    /// <param name="instructions">The instructions defining the score.</param>
    /// <param name="levels">The ordered, caller-defined score levels.</param>
    [JsonConstructor]
    public ScoreDecisionQuestion(string id, string? instructions, IReadOnlyList<DecisionScoreLevel> levels)
        : base(id, DecisionKind.Score, instructions)
    {
        _ = Throw.IfNull(levels);

        DecisionScoreLevel[] copy = levels.ToArray();
        if (copy.Length < 2 || Array.Exists(copy, static level => level is null))
        {
            Throw.ArgumentException(nameof(levels), "A score question requires at least two levels.");
        }

        HashSet<string> ids = new(StringComparer.Ordinal);
        foreach (DecisionScoreLevel level in copy)
        {
            if (!ids.Add(level.Id))
            {
                Throw.ArgumentException(
                    nameof(levels),
                    "Score level IDs must be unique using ordinal comparison.");
            }
        }

        Levels = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the ordered, owned score-level snapshot.</summary>
    public IReadOnlyList<DecisionScoreLevel> Levels { get; }
}

/// <summary>Represents a state and a nonempty, ordered batch of questions.</summary>
[Experimental(DiagnosticIds.Experiments.AIDecisions, UrlFormat = DiagnosticIds.UrlFormat)]
public sealed class DecisionRequest
{
    /// <summary>Initializes a new instance of the <see cref="DecisionRequest"/> class and snapshots its state and questions.</summary>
    /// <param name="state">The explicit JSON state evaluated by every question.</param>
    /// <param name="questions">The ordered heterogeneous question batch.</param>
    [JsonConstructor]
    public DecisionRequest(JsonElement state, IReadOnlyList<DecisionQuestion> questions)
    {
        if (state.ValueKind == JsonValueKind.Undefined)
        {
            Throw.ArgumentException(nameof(state), "State must be explicit JSON.");
        }

        _ = Throw.IfNull(questions);

        DecisionQuestion[] copy = questions.ToArray();
        if (copy.Length == 0 || Array.Exists(copy, static question => question is null))
        {
            Throw.ArgumentException(nameof(questions), "Questions must be nonempty.");
        }

        HashSet<string> ids = new(StringComparer.Ordinal);
        foreach (DecisionQuestion question in copy)
        {
            if (!ids.Add(question.Id))
            {
                Throw.ArgumentException(
                    nameof(questions),
                    "Question IDs must be unique using ordinal comparison.");
            }
        }

        State = state.Clone();
        Questions = Array.AsReadOnly(copy);
    }

    /// <summary>Gets the owned JSON state snapshot.</summary>
    public JsonElement State { get; }

    /// <summary>Gets the ordered, owned question snapshot.</summary>
    public IReadOnlyList<DecisionQuestion> Questions { get; }

    /// <summary>Creates a request from an application-owned state using an explicit source-generated contract.</summary>
    /// <typeparam name="TState">The application state type.</typeparam>
    /// <param name="state">The application-owned state.</param>
    /// <param name="stateTypeInfo">The source-generated JSON contract for <typeparamref name="TState"/>.</param>
    /// <param name="questions">The ordered heterogeneous question batch.</param>
    /// <returns>An owned decision request.</returns>
    public static DecisionRequest Create<TState>(
        TState state,
        JsonTypeInfo<TState> stateTypeInfo,
        IEnumerable<DecisionQuestion> questions)
    {
        _ = Throw.IfNull(stateTypeInfo);
        _ = Throw.IfNull(questions);
        return new(JsonSerializer.SerializeToElement(state, stateTypeInfo), questions.ToArray());
    }
}
