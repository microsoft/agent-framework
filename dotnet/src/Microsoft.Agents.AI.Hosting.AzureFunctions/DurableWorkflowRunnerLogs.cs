// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Logging messages for <see cref="DurableWorkflowRunner"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class DurableWorkflowRunnerLogs
{
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Attempting to run workflow: {WorkflowName}")]
    public static partial void LogAttemptingToRunWorkflow(this ILogger logger, string workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Running workflow: {WorkflowName}")]
    public static partial void LogRunningWorkflow(this ILogger logger, string? workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Attempting to execute activity in workflow '{WorkflowName}' for executor '{ExecutorName}'")]
    public static partial void LogAttemptingToExecuteActivity(this ILogger logger, string workflowName, string executorName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Executing activity for executor '{ExecutorId}' of type '{ExecutorType}'")]
    public static partial void LogExecutingActivity(this ILogger logger, string executorId, string executorType);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Activity executed for executor '{ExecutorId}' with result: {Result}")]
    public static partial void LogActivityExecuted(this ILogger logger, string executorId, string result);
}
