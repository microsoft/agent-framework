// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>Source-generated log messages for the agent-hooks enforcement.</summary>
internal static partial class AgentHooksLogMessages
{
    [LoggerMessage(
        EventId = 1,
        Level = LogLevel.Warning,
        Message = "agent-hooks failed to emit agent_shutdown (reason: {Reason}); the session trail is incomplete.")]
    public static partial void LogAgentShutdownEmissionFailed(this ILogger logger, string reason, Exception exception);
}
