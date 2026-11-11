// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// The questions asked about one tool argument and how its value is read from the answers.
/// </summary>
internal sealed class DecisionArgumentPlan
{
    public required string Name { get; init; }

    public required DecisionArgumentKind Kind { get; init; }

    /// <summary>
    /// Gets the ID of the Binary question that decides whether an optional argument is passed at all, or
    /// <see langword="null"/> for a required argument.
    /// </summary>
    public string? PresenceQuestionId { get; init; }

    /// <summary>Gets the ID of the Choice or Binary question of a <see cref="DecisionArgumentKind.Choice"/> or <see cref="DecisionArgumentKind.Boolean"/> argument.</summary>
    public string? ValueQuestionId { get; init; }

    /// <summary>Gets the enum values of a <see cref="DecisionArgumentKind.Choice"/> argument, keyed by their Choice label.</summary>
    public IReadOnlyDictionary<string, JsonElement> Values { get; init; } = new Dictionary<string, JsonElement>();

    /// <summary>Gets the Binary question ID and the value of each member of a <see cref="DecisionArgumentKind.Set"/> argument.</summary>
    public IReadOnlyList<KeyValuePair<string, JsonElement>> Members { get; init; } = [];

    /// <summary>Gets the value of a <see cref="DecisionArgumentKind.Const"/> argument.</summary>
    public JsonElement ConstValue { get; init; }

    /// <summary>
    /// Reads the argument value from the answers.
    /// </summary>
    /// <returns>
    /// <see langword="false"/> when an optional argument should be left out, so that the function uses its default.
    /// </returns>
    public bool TryDecode(DecisionResponse response, out JsonElement value)
    {
        value = default;
        if (this.PresenceQuestionId is not null && !DecisionToolCallPlan.IsYes(response, this.PresenceQuestionId))
        {
            return false;
        }

        switch (this.Kind)
        {
            case DecisionArgumentKind.Const:
                value = this.ConstValue;
                return true;

            case DecisionArgumentKind.Boolean:
                value = DecisionJson.CreateBoolean(DecisionToolCallPlan.IsYes(response, this.ValueQuestionId!));
                return true;

            case DecisionArgumentKind.Choice:
                string label = DecisionToolCallPlan.GetChoice(response, this.ValueQuestionId!);
                if (!this.Values.TryGetValue(label, out value))
                {
                    Throw.InvalidOperationException($"The decision model returned the unknown choice '{label}' for the tool argument '{this.Name}'.");
                }

                return true;

            case DecisionArgumentKind.Set:
                value = DecisionJson.CreateArray(this.Members.Where(member => DecisionToolCallPlan.IsYes(response, member.Key)).Select(member => member.Value));
                return true;

            default:
                Throw.InvalidOperationException($"The argument plan of '{this.Name}' has the unknown kind {this.Kind}.");
                return false;
        }
    }
}
