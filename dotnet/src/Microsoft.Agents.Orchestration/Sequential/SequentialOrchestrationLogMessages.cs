// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Extensions for logging <see cref="SequentialOrchestration{TInput, TOutput}"/>.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class SequentialOrchestrationLogMessages
{
    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "REQUEST Sequential agent [{AgentId}]")]
    public static partial void LogSequentialAgentInvoke(
        this ILogger logger,
        ActorId agentId);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "RESULT Sequential agent [{AgentId}]: {Message}")]
    public static partial void LogSequentialAgentResult(
        this ILogger logger,
        ActorId agentId,
        string? message);
}
