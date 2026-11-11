// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>Source-generated log messages of <see cref="DecisionChatEngine"/>.</summary>
internal static partial class DecisionChatLog
{
    [LoggerMessage(
        EventId = 1,
        Level = LogLevel.Warning,
        Message = "The tool '{ToolName}' is left out of the {ModelName} request because its parameters cannot be expressed as closed-set questions: {Reason}")]
    public static partial void LogToolExcluded(this ILogger logger, string modelName, string toolName, string reason);
}
