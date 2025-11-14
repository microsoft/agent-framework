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
}
