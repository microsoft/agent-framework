// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Provides helper methods for workflow naming conventions used in durable orchestrations.
/// </summary>
internal static class WorkflowNamingHelper
{
    internal const string OrchestrationFunctionPrefix = "dafx-";
    private const char ExecutorIdSuffixSeparator = '_';

    /// <summary>
    /// Converts a workflow name to its corresponding orchestration function name.
    /// </summary>
    /// <param name="workflowName">The workflow name.</param>
    /// <returns>The orchestration function name.</returns>
    /// <exception cref="ArgumentException">Thrown when the workflow name is null or empty.</exception>
    internal static string ToOrchestrationFunctionName(string workflowName)
    {
        ArgumentException.ThrowIfNullOrEmpty(workflowName);
        return string.Concat(OrchestrationFunctionPrefix, workflowName);
    }

    /// <summary>
    /// Converts an orchestration function name back to its workflow name.
    /// </summary>
    /// <param name="orchestrationFunctionName">The orchestration function name.</param>
    /// <returns>The workflow name.</returns>
    /// <exception cref="ArgumentException">Thrown when the orchestration function name is null, empty, or doesn't have the expected prefix.</exception>
    internal static string ToWorkflowName(string orchestrationFunctionName)
    {
        ArgumentException.ThrowIfNullOrEmpty(orchestrationFunctionName);

        if (!TryGetWorkflowName(orchestrationFunctionName, out string? workflowName) || workflowName is null)
        {
            throw new ArgumentException(
                $"Orchestration function name '{orchestrationFunctionName}' does not have the expected '{OrchestrationFunctionPrefix}' prefix or is missing a workflow name.",
                nameof(orchestrationFunctionName));
        }

        return workflowName;
    }

    /// <summary>
    /// Extracts the executor name from an executor ID.
    /// </summary>
    /// <remarks>
    /// <para>
    /// For non-agentic executors, the executor ID is the same as the executor name (e.g., "OrderParser").
    /// </para>
    /// <para>
    /// For agentic executors, the workflow builder appends a GUID suffix separated by an underscore
    /// (e.g., "Physicist_8884e71021334ce49517fa2b17b1695b"). This method extracts just the name portion.
    /// </para>
    /// </remarks>
    /// <param name="executorId">The executor ID, which may contain a GUID suffix.</param>
    /// <returns>The executor name without any GUID suffix.</returns>
    /// <exception cref="ArgumentException">Thrown when the executor ID is null or empty.</exception>
    internal static string GetExecutorName(string executorId)
    {
        ArgumentException.ThrowIfNullOrEmpty(executorId);

        int separatorIndex = executorId.IndexOf(ExecutorIdSuffixSeparator);
        return separatorIndex > 0 ? executorId[..separatorIndex] : executorId;
    }

    private static bool TryGetWorkflowName(string? orchestrationFunctionName, out string? workflowName)
    {
        workflowName = null;

        if (string.IsNullOrEmpty(orchestrationFunctionName) ||
            !orchestrationFunctionName.StartsWith(OrchestrationFunctionPrefix, StringComparison.Ordinal))
        {
            return false;
        }

        workflowName = orchestrationFunctionName[OrchestrationFunctionPrefix.Length..];
        return workflowName.Length > 0;
    }
}
