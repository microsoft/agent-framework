// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions.Workflows;

/// <summary>
/// Logging messages for <see cref="DurableWorkflowFunctionMetadataTransformer"/>.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class DurableWorkflowFunctionMetadataTransformerLogs
{
    [LoggerMessage(
        EventId = 200,
        Level = LogLevel.Information,
        Message = "Transforming function metadata to add durable workflow functions. Initial function count: {FunctionCount}")]
    public static partial void LogTransformStart(this ILogger logger, int functionCount);

    [LoggerMessage(
        EventId = 201,
        Level = LogLevel.Information,
        Message = "Adding durable workflow function for workflow: {WorkflowName}")]
    public static partial void LogAddingWorkflowFunction(this ILogger logger, string workflowName);

    [LoggerMessage(
        EventId = 202,
        Level = LogLevel.Information,
        Message = "Adding HTTP trigger function for workflow: {WorkflowName}")]
    public static partial void LogAddingHttpTrigger(this ILogger logger, string workflowName);

    [LoggerMessage(
        EventId = 203,
        Level = LogLevel.Information,
        Message = "Adding activity function for executor: {ExecutorId} (Type: {ExecutorType}) in workflow: {WorkflowName}")]
    public static partial void LogAddingActivityFunction(this ILogger logger, string executorId, string executorType, string workflowName);

    [LoggerMessage(
        EventId = 204,
        Level = LogLevel.Information,
        Message = "Adding agent entity function for executor: {ExecutorId} (Type: {ExecutorType}) in workflow: {WorkflowName}")]
    public static partial void LogAddingAgentEntityFunction(this ILogger logger, string executorId, string executorType, string workflowName);

    [LoggerMessage(
        EventId = 205,
        Level = LogLevel.Information,
        Message = "Adding MCP tool trigger function for workflow: {WorkflowName}")]
    public static partial void LogAddingMcpToolTrigger(this ILogger logger, string workflowName);

    [LoggerMessage(
        EventId = 206,
        Level = LogLevel.Information,
        Message = "Transform finished. Updated function count: {FunctionCount}")]
    public static partial void LogTransformFinished(this ILogger logger, int functionCount);

    [LoggerMessage(
        EventId = 207,
        Level = LogLevel.Debug,
        Message = "Skipping duplicate function registration: {FunctionName} (already registered by another workflow) in workflow: {WorkflowName}")]
    public static partial void LogSkippingDuplicateFunction(this ILogger logger, string functionName, string workflowName);
}
