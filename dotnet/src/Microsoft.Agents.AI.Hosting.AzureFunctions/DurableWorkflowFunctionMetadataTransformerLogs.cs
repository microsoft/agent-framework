// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Logging messages for <see cref="DurableWorkflowFunctionMetadataTransformer"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class DurableWorkflowFunctionMetadataTransformerLogs
{
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Transforming function metadata to add durable workflow functions. Initial function count: {FunctionCount}")]
    public static partial void LogTransformStart(this ILogger logger, int functionCount);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Adding durable workflow function for workflow: {WorkflowName}")]
    public static partial void LogAddingWorkflowFunction(this ILogger logger, string workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Adding HTTP trigger function for workflow: {WorkflowName}")]
    public static partial void LogAddingHttpTrigger(this ILogger logger, string workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Adding activity function for executor: {ExecutorId} (Type: {ExecutorType}) in workflow: {WorkflowName}")]
    public static partial void LogAddingActivityFunction(this ILogger logger, string executorId, string executorType, string workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Adding agent entity function for executor: {ExecutorId} (Type: {ExecutorType}) in workflow: {WorkflowName}")]
    public static partial void LogAddingAgentEntityFunction(this ILogger logger, string executorId, string executorType, string workflowName);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Transform finished. Updated function count: {FunctionCount}")]
    public static partial void LogTransformFinished(this ILogger logger, int functionCount);
}
