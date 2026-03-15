// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI;
#pragma warning disable SYSLIB1006 // Multiple logging methods cannot use the same event id within a class

/// <summary>
/// Extensions for logging <see cref="ChatClientAgent"/> invocations.
/// </summary>
/// <remarks>
/// This extension uses the <see cref="LoggerMessageAttribute"/> to
/// generate logging code at compile time to achieve optimized code.
/// </remarks>
[ExcludeFromCodeCoverage]
internal static partial class ChatClientAgentLogMessages
{
    /// <summary>
    /// Logs <see cref="ChatClientAgent"/> invoking agent (started).
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "[{MethodName}] Agent {AgentId}/{AgentName} Invoking client {ClientType}.")]
    public static partial void LogAgentChatClientInvokingAgent(
        this ILogger logger,
        string methodName,
        string agentId,
        string agentName,
        Type clientType);

    /// <summary>
    /// Logs <see cref="ChatClientAgent"/> invoked agent (complete).
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "[{MethodName}] Agent {AgentId}/{AgentName} Invoked client {ClientType} with message count: {MessageCount}.")]
    public static partial void LogAgentChatClientInvokedAgent(
        this ILogger logger,
        string methodName,
        string agentId,
        string agentName,
        Type clientType,
        int messageCount);

    /// <summary>
    /// Logs <see cref="ChatClientAgent"/> invoked streaming agent (complete).
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "[{MethodName}] Agent {AgentId}/{AgentName} Invoked client {ClientType}.")]
    public static partial void LogAgentChatClientInvokedStreamingAgent(
        this ILogger logger,
        string methodName,
        string agentId,
        string agentName,
        Type clientType);

    /// <summary>
    /// Logs <see cref="ChatClientAgent"/> warning about <see cref="ChatHistoryProvider"/> conflict.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Agent {AgentId}/{AgentName}: Only {ConversationIdName} or {ChatHistoryProviderName} may be used, but not both. The service returned a conversation id indicating server-side chat history management, but the agent has a {ChatHistoryProviderName} configured.")]
    public static partial void LogAgentChatClientHistoryProviderConflict(
        this ILogger logger,
        string conversationIdName,
        string chatHistoryProviderName,
        string agentId,
        string agentName);
}
