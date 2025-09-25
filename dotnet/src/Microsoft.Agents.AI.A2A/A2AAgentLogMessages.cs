// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Extensions for logging <see cref="A2AAgent"/> invocations.
/// </summary>
[ExcludeFromCodeCoverage]
internal static partial class A2AAgentLogMessages
{
    /// <summary>
    /// Logs <see cref="A2AAgent"/> invoking agent (started).
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "[{MethodName}] A2AAgent {AgentId}/{AgentName} invoking underlying A2A agent.")]
    public static partial void LogA2AAgentInvokingAgent(
        this ILogger logger,
        string methodName,
        string agentId,
        string? agentName);

    /// <summary>
    /// Logs <see cref="A2AAgent"/> invoked agent (complete).
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "[{MethodName}] A2AAgent {AgentId}/{AgentName} invoked underlying A2A agent.")]
    public static partial void LogAgentChatClientInvokedAgent(
        this ILogger logger,
        string methodName,
        string agentId,
        string? agentName);
}
