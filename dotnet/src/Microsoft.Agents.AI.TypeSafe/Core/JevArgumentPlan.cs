// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The questions asked about one tool argument and how its value is read from the answers.
/// </summary>
internal sealed class JevArgumentPlan
{
    public required string Name { get; init; }

    public required JevArgumentKind Kind { get; init; }

    /// <summary>
    /// Gets the ID of the Noul question that decides whether an optional argument is passed at all, or
    /// <see langword="null"/> for a required argument.
    /// </summary>
    public string? PresenceQuestionId { get; init; }

    /// <summary>Gets the ID of the Choice or Noul question of a <see cref="JevArgumentKind.Choice"/> or <see cref="JevArgumentKind.Boolean"/> argument.</summary>
    public string? ValueQuestionId { get; init; }

    /// <summary>Gets the enum values of a <see cref="JevArgumentKind.Choice"/> argument, keyed by their Choice label.</summary>
    public IReadOnlyDictionary<string, JsonElement> Values { get; init; } = new Dictionary<string, JsonElement>();

    /// <summary>Gets the Noul question ID and the value of each member of a <see cref="JevArgumentKind.Set"/> argument.</summary>
    public IReadOnlyList<KeyValuePair<string, JsonElement>> Members { get; init; } = [];

    /// <summary>Gets the value of a <see cref="JevArgumentKind.Const"/> argument.</summary>
    public JsonElement ConstValue { get; init; }

    /// <summary>
    /// Reads the argument value from Jev's answers.
    /// </summary>
    /// <returns>
    /// <see langword="false"/> when an optional argument should be left out, so that the function uses its default.
    /// </returns>
    public bool TryDecode(JevResult result, out JsonElement value)
    {
        value = default;
        if (this.PresenceQuestionId is not null && !JevToolCallPlan.IsYes(result, this.PresenceQuestionId))
        {
            return false;
        }

        switch (this.Kind)
        {
            case JevArgumentKind.Const:
                value = this.ConstValue;
                return true;

            case JevArgumentKind.Boolean:
                value = JevJsonUtilities.CreateBoolean(JevToolCallPlan.IsYes(result, this.ValueQuestionId!));
                return true;

            case JevArgumentKind.Choice:
                string label = JevToolCallPlan.GetChoice(result, this.ValueQuestionId!);
                if (!this.Values.TryGetValue(label, out value))
                {
                    Throw.InvalidOperationException($"Jev returned the unknown choice '{label}' for the tool argument '{this.Name}'.");
                }

                return true;

            case JevArgumentKind.Set:
                value = JevJsonUtilities.CreateArray(this.Members.Where(member => JevToolCallPlan.IsYes(result, member.Key)).Select(member => member.Value));
                return true;

            default:
                Throw.InvalidOperationException($"The argument plan of '{this.Name}' has the unknown kind {this.Kind}.");
                return false;
        }
    }
}
