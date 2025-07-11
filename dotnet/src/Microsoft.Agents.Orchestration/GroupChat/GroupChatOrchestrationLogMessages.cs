// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Extensions for logging <see cref="GroupChatOrchestration{TInput, TOutput}"/>.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class GroupChatOrchestrationLogMessages
{
    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "CHAT AGENT invoked [{AgentId}]")]
    public static partial void LogChatAgentInvoke(
        this ILogger logger,
        ActorId agentId);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "CHAT AGENT result [{AgentId}]: {Message}")]
    public static partial void LogChatAgentResult(
        this ILogger logger,
        ActorId agentId,
        string? message);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER initialized [{AgentId}]")]
    public static partial void LogChatManagerInit(
        this ILogger logger,
        ActorId agentId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER invoked [{AgentId}]")]
    public static partial void LogChatManagerInvoke(
        this ILogger logger,
        ActorId agentId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER terminate? [{AgentId}]: {Result} ({Reason})")]
    public static partial void LogChatManagerTerminate(
        this ILogger logger,
        ActorId agentId,
        bool result,
        string reason);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER select: {NextAgent} [{AgentId}]")]
    public static partial void LogChatManagerSelect(
        this ILogger logger,
        ActorId agentId,
        ActorType nextAgent);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER result [{AgentId}]: '{Result}' ({Reason})")]
    public static partial void LogChatManagerResult(
        this ILogger logger,
        ActorId agentId,
        string result,
        string reason);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "CHAT MANAGER user-input? [{AgentId}]: {Result} ({Reason})")]
    public static partial void LogChatManagerInput(
        this ILogger logger,
        ActorId agentId,
        bool result,
        string reason);

    [LoggerMessage(
        Level = LogLevel.Trace,
        Message = "CHAT AGENT user-input [{AgentId}]: {Message}")]
    public static partial void LogChatManagerUserInput(
        this ILogger logger,
        ActorId agentId,
        string? message);
}
