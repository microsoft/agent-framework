// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.Orchestration.Handoff;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Extensions for logging <see cref="HandoffOrchestration{TInput, TOutput}"/>.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class HandoffOrchestrationLogMessages
{
    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "REQUEST Handoff agent [{AgentId}]")]
    public static partial void LogHandoffAgentInvoke(
        this ILogger logger,
        ActorId agentId);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "RESULT Handoff agent [{AgentId}]: {Message}")]
    public static partial void LogHandoffAgentResult(
        this ILogger logger,
        ActorId agentId,
        string? message);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "TOOL Handoff [{AgentId}]: {Name}")]
    public static partial void LogHandoffFunctionCall(
        this ILogger logger,
        ActorId agentId,
        string name);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "RESULT Handoff summary [{AgentId}]: {Summary}")]
    public static partial void LogHandoffSummary(
        this ILogger logger,
        ActorId agentId,
        string? summary);
}
