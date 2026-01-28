// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Provides helper methods for workflow naming conventions used in durable orchestrations.
/// </summary>
internal static class WorkflowNamingHelper
{
    /// <summary>
    /// The prefix used for durable workflow orchestration function names.
    /// </summary>
    public const string OrchestrationFunctionPrefix = "dafx-";

    /// <summary>
    /// Converts a workflow name to its corresponding orchestration function name.
    /// </summary>
    /// <param name="workflowName">The workflow name.</param>
    /// <returns>The orchestration function name.</returns>
    /// <exception cref="ArgumentException">Thrown when the workflow name is null or empty.</exception>
    public static string ToOrchestrationFunctionName(string workflowName)
    {
        ArgumentException.ThrowIfNullOrEmpty(workflowName);
        return $"{OrchestrationFunctionPrefix}{workflowName}";
    }

    /// <summary>
    /// Converts an orchestration function name back to its workflow name.
    /// </summary>
    /// <param name="orchestrationFunctionName">The orchestration function name.</param>
    /// <returns>The workflow name.</returns>
    /// <exception cref="ArgumentException">Thrown when the orchestration function name is null, empty, or doesn't have the expected prefix.</exception>
    public static string ToWorkflowName(string orchestrationFunctionName)
    {
        ArgumentException.ThrowIfNullOrEmpty(orchestrationFunctionName);

        if (!orchestrationFunctionName.StartsWith(OrchestrationFunctionPrefix, StringComparison.Ordinal))
        {
            throw new ArgumentException(
                $"Orchestration function name '{orchestrationFunctionName}' does not start with the expected '{OrchestrationFunctionPrefix}' prefix.",
                nameof(orchestrationFunctionName));
        }

        string workflowName = orchestrationFunctionName[OrchestrationFunctionPrefix.Length..];

        if (string.IsNullOrEmpty(workflowName))
        {
            throw new ArgumentException(
                $"Orchestration function name '{orchestrationFunctionName}' does not contain a workflow name after the prefix.",
                nameof(orchestrationFunctionName));
        }

        return workflowName;
    }

    /// <summary>
    /// Tries to convert an orchestration function name back to its workflow name.
    /// </summary>
    /// <param name="orchestrationFunctionName">The orchestration function name.</param>
    /// <param name="workflowName">When this method returns, contains the workflow name if the conversion succeeded, or null if it failed.</param>
    /// <returns><c>true</c> if the conversion succeeded; otherwise, <c>false</c>.</returns>
    public static bool TryGetWorkflowName(string? orchestrationFunctionName, out string? workflowName)
    {
        workflowName = null;

        if (string.IsNullOrEmpty(orchestrationFunctionName))
        {
            return false;
        }

        if (!orchestrationFunctionName.StartsWith(OrchestrationFunctionPrefix, StringComparison.Ordinal))
        {
            return false;
        }

        workflowName = orchestrationFunctionName[OrchestrationFunctionPrefix.Length..];
        return !string.IsNullOrEmpty(workflowName);
    }

    /// <summary>
    /// The suffix separator used when the workflow builder appends a GUID to executor IDs.
    /// </summary>
    /// <remarks>
    /// For agentic executors, the workflow builder appends a GUID suffix to ensure uniqueness.
    /// For example: "Physicist_8884e71021334ce49517fa2b17b1695b".
    /// </remarks>
    private const char ExecutorIdSuffixSeparator = '_';

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
    public static string GetExecutorName(string executorId)
    {
        ArgumentException.ThrowIfNullOrEmpty(executorId);

        int separatorIndex = executorId.IndexOf(ExecutorIdSuffixSeparator);
        return separatorIndex > 0 ? executorId[..separatorIndex] : executorId;
    }

    /// <summary>
    /// Determines whether the executor ID contains a GUID suffix.
    /// </summary>
    /// <param name="executorId">The executor ID to check.</param>
    /// <returns><c>true</c> if the executor ID contains a suffix; otherwise, <c>false</c>.</returns>
    public static bool HasExecutorIdSuffix(string? executorId)
    {
        if (string.IsNullOrEmpty(executorId))
        {
            return false;
        }

        int separatorIndex = executorId.IndexOf(ExecutorIdSuffixSeparator);
        return separatorIndex > 0 && separatorIndex < executorId.Length - 1;
    }
}
