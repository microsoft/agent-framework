// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.RegularExpressions;

namespace AGUIDojoClient.Components.Demos.AgenticGenerativeUI;

/// <summary>
/// Applies JSON Patch operations to a Plan object.
/// </summary>
public static partial class PlanPatcher
{
    /// <summary>
    /// Applies a list of JSON Patch operations to the given plan.
    /// </summary>
    /// <param name="plan">The plan to modify.</param>
    /// <param name="operations">The patch operations to apply.</param>
    public static void Apply(Plan plan, IEnumerable<JsonPatchOperation> operations)
    {
        foreach (var operation in operations)
        {
            ApplyOperation(plan, operation);
        }
    }

    private static void ApplyOperation(Plan plan, JsonPatchOperation operation)
    {
        // Parse paths like "/steps/0/status" or "/steps/0/description"
        var match = StepPathRegex().Match(operation.Path);
        if (!match.Success)
        {
            return;
        }

        if (!int.TryParse(match.Groups["index"].Value, out var index))
        {
            return;
        }

        if (index < 0 || index >= plan.Steps.Count)
        {
            return;
        }

        var property = match.Groups["property"].Value;
        var step = plan.Steps[index];

        if (string.Equals(operation.Op, "replace", StringComparison.OrdinalIgnoreCase))
        {
            if (string.Equals(property, "status", StringComparison.OrdinalIgnoreCase))
            {
                step.Status = GetStringValue(operation.Value) ?? step.Status;
            }
            else if (string.Equals(property, "description", StringComparison.OrdinalIgnoreCase))
            {
                step.Description = GetStringValue(operation.Value) ?? step.Description;
            }
        }
    }

    private static string? GetStringValue(object? value)
    {
        return value switch
        {
            string s => s,
            JsonElement { ValueKind: JsonValueKind.String } je => je.GetString(),
            _ => value?.ToString()
        };
    }

    [GeneratedRegex(@"^/steps/(?<index>\d+)/(?<property>\w+)$")]
    private static partial Regex StepPathRegex();
}
