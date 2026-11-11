// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// One tool that can be expressed as decision questions: its route label, its argument questions, and their decoders.
/// </summary>
internal sealed class DecisionCompiledTool
{
    public required AIFunctionDeclaration Function { get; init; }

    /// <summary>Gets the label of the tool in the route question, such as <c>t0</c>.</summary>
    public required string RouteLabel { get; init; }

    public required IReadOnlyDictionary<string, DecisionQuestion> Questions { get; init; }

    public required IReadOnlyList<DecisionArgumentPlan> Arguments { get; init; }

    public Dictionary<string, object?> DecodeArguments(DecisionResponse response)
    {
        var arguments = new Dictionary<string, object?>(this.Arguments.Count);
        foreach (DecisionArgumentPlan argument in this.Arguments)
        {
            if (argument.TryDecode(response, out JsonElement value))
            {
                arguments[argument.Name] = value;
            }
        }

        return arguments;
    }
}
