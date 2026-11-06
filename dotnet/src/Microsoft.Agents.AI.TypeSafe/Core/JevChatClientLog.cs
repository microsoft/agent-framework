// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>Source-generated log messages of <see cref="JevChatClient"/>.</summary>
internal static partial class JevChatClientLog
{
    [LoggerMessage(
        EventId = 1,
        Level = LogLevel.Warning,
        Message = "The tool '{ToolName}' is left out of the Jev request because its parameters cannot be expressed as Jev questions: {Reason}")]
    public static partial void LogToolExcluded(this ILogger logger, string toolName, string reason);
}
