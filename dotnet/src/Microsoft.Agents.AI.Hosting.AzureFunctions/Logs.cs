// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal static partial class Logs
{
    [LoggerMessage(
        EventId = 100,
        Level = LogLevel.Information,
        Message = "Transforming function metadata to add durable agent functions. Initial function count: {FunctionCount}")]
    public static partial void LogTransformingFunctionMetadata(this ILogger logger, int functionCount);

    [LoggerMessage(
        EventId = 101,
        Level = LogLevel.Information,
        Message = "Registering {TriggerType} function for agent '{AgentName}'")]
    public static partial void LogRegisteringTriggerForAgent(this ILogger logger, string agentName, string triggerType);

    [LoggerMessage(
        EventId = 102,
        Level = LogLevel.Information,
        Message = "Registering {TriggerType} trigger function '{FunctionName}' for workflow '{WorkflowKey}'")]
    public static partial void LogRegisteringWorkflowTrigger(this ILogger logger, string workflowKey, string functionName, string triggerType);

    [LoggerMessage(
        EventId = 103,
        Level = LogLevel.Information,
        Message = "Function metadata transformation complete. Added {AddedCount} workflow function(s). Total function count: {TotalCount}")]
    public static partial void LogTransformationComplete(this ILogger logger, int addedCount, int totalCount);
}
