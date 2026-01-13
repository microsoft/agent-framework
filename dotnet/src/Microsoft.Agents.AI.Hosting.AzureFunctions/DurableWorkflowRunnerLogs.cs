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
}
