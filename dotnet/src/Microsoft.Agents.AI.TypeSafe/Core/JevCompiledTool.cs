// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// One tool that can be expressed as Jev questions: its route label, its argument questions, and their decoders.
/// </summary>
internal sealed class JevCompiledTool
{
    public required AIFunctionDeclaration Function { get; init; }

    /// <summary>Gets the label of the tool in the route question, such as <c>t0</c>.</summary>
    public required string RouteLabel { get; init; }

    public required IReadOnlyDictionary<string, JevQuestion> Questions { get; init; }

    public required IReadOnlyList<JevArgumentPlan> Arguments { get; init; }

    public Dictionary<string, object?> DecodeArguments(JevResult result)
    {
        var arguments = new Dictionary<string, object?>(this.Arguments.Count);
        foreach (JevArgumentPlan argument in this.Arguments)
        {
            if (argument.TryDecode(result, out JsonElement value))
            {
                arguments[argument.Name] = value;
            }
        }

        return arguments;
    }
}
