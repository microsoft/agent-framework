// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a request to an <see cref="IDecisionClient"/>: a piece of application state and the typed questions to
/// evaluate against it.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="State"/> is a <see cref="JsonElement"/> rather than an arbitrary object so that the serialization boundary
/// is explicit and trimming/Native AOT friendly. It may be a JSON object, an array, a string, or a scalar. Use
/// <see cref="DecisionClientExtensions.GetResponseAsync{TState}"/> to supply strongly typed state through a
/// <see cref="System.Text.Json.Serialization.Metadata.JsonTypeInfo{T}"/>.
/// </para>
/// <para>
/// Every question is evaluated against the same state. Question identifiers must be unique within a request; they are
/// application correlation keys and carry no model semantics.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionRequest
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionRequest"/> class.
    /// </summary>
    /// <param name="state">The state to evaluate.</param>
    /// <param name="questions">The questions to ask about the state.</param>
    /// <exception cref="ArgumentNullException"><paramref name="questions"/> is <see langword="null"/> or contains a <see langword="null"/> element.</exception>
    /// <exception cref="ArgumentException"><paramref name="questions"/> contains two questions with the same <see cref="DecisionQuestion.Id"/>.</exception>
    public DecisionRequest(JsonElement state, IEnumerable<DecisionQuestion> questions)
    {
        _ = Throw.IfNull(questions);

        this.State = state;

        var list = new List<DecisionQuestion>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (DecisionQuestion question in questions)
        {
            _ = Throw.IfNull(question, nameof(questions));
            if (!ids.Add(question.Id))
            {
                throw new ArgumentException($"Question ids must be unique within a request; '{question.Id}' appears more than once.", nameof(questions));
            }

            list.Add(question);
        }

        this.Questions = list;
    }

    /// <summary>Gets or sets the state that every question is evaluated against.</summary>
    public JsonElement State { get; set; }

    /// <summary>Gets the questions to ask about <see cref="State"/>.</summary>
    /// <remarks>
    /// The list is mutable so callers can add questions after construction. Providers validate that identifiers are
    /// unique and non-empty at call time.
    /// </remarks>
    public IList<DecisionQuestion> Questions { get; }
}
