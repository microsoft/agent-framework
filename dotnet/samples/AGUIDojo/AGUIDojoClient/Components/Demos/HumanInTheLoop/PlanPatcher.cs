// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;

namespace AGUIDojoClient.Components.Demos.HumanInTheLoop;

/// <summary>
/// Applies JSON Patch operations to a Plan.
/// Uses hardcoded path parsing for the expected paths:
/// - /steps/{index}/status
/// - /steps/{index}/description
/// </summary>
public static partial class PlanPatcher
{
    // Regex to match paths like /steps/0/status or /steps/1/description
    [GeneratedRegex(@"^/steps/(\d+)/(status|description)$")]
    private static partial Regex StepPropertyPathRegex();

    /// <summary>
    /// Applies a JSON Patch operation to the plan.
    /// Only supports "replace" operations on /steps/{index}/status and /steps/{index}/description paths.
    /// </summary>
    /// <param name="plan">The plan to modify.</param>
    /// <param name="operation">The patch operation to apply.</param>
    /// <returns>True if the operation was applied successfully, false otherwise.</returns>
    public static bool ApplyPatch(Plan plan, JsonPatchOperation operation)
    {
        ArgumentNullException.ThrowIfNull(plan);
        ArgumentNullException.ThrowIfNull(operation);

        // Only support "replace" operations
        if (!string.Equals(operation.Op, "replace", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var match = StepPropertyPathRegex().Match(operation.Path);
        if (!match.Success)
        {
            return false;
        }

        if (!int.TryParse(match.Groups[1].Value, out int stepIndex))
        {
            return false;
        }

        if (stepIndex < 0 || stepIndex >= plan.Steps.Count)
        {
            return false;
        }

        var propertyName = match.Groups[2].Value;
        var step = plan.Steps[stepIndex];

        switch (propertyName.ToUpperInvariant())
        {
            case "STATUS":
                step.Status = operation.Value?.ToString() ?? "pending";
                return true;
            case "DESCRIPTION":
                step.Description = operation.Value?.ToString() ?? string.Empty;
                return true;
            default:
                return false;
        }
    }

    /// <summary>
    /// Applies multiple JSON Patch operations to the plan.
    /// </summary>
    /// <param name="plan">The plan to modify.</param>
    /// <param name="operations">The patch operations to apply.</param>
    /// <returns>The number of operations successfully applied.</returns>
    public static int ApplyPatches(Plan plan, IEnumerable<JsonPatchOperation> operations)
    {
        int appliedCount = 0;
        foreach (var operation in operations)
        {
            if (ApplyPatch(plan, operation))
            {
                appliedCount++;
            }
        }
        return appliedCount;
    }
}
