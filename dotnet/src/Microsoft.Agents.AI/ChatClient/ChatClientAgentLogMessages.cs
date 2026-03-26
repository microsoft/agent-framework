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

    /// <summary>
    /// Logs a warning when <see cref="ChatClientAgentOptions.UseProvidedChatClientAsIs"/> is <see langword="true"/>
    /// and <see cref="ChatClientAgentOptions.PersistChatHistoryAtEndOfRun"/> is <see langword="true"/>,
    /// but no <see cref="ChatHistoryPersistingChatClient"/> is found in the custom chat client stack.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Agent {AgentId}/{AgentName}: PersistChatHistoryAtEndOfRun is enabled with a custom chat client stack (UseProvidedChatClientAsIs), but no ChatHistoryPersistingChatClient was found in the pipeline. All messages will be persisted at the end of the run without marking. This setup is not supported with some other features, e.g. handoffs. Consider adding a ChatHistoryPersistingChatClient to the pipeline using the UseChatHistoryPersisting extension method.")]
    public static partial void LogAgentChatClientMissingPersistingClient(
        this ILogger logger,
        string agentId,
        string agentName);

    /// <summary>
    /// Logs a warning when per-service-call persistence falls back to end-of-run persistence
    /// because the run involves background responses (continuation token resumption or
    /// <c>AllowBackgroundResponses</c>). Per-service-call persistence is
    /// unreliable in these scenarios because the caller may stop consuming the stream before
    /// the decorator's post-stream persistence code can execute.
    /// </summary>
    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Agent {AgentId}/{AgentName}: Per-service-call persistence is falling back to end-of-run persistence because the run involves background responses. Messages will be marked during the run and persisted at the end.")]
    public static partial void LogAgentChatClientBackgroundResponseFallback(
        this ILogger logger,
        string agentId,
        string agentName);
}
