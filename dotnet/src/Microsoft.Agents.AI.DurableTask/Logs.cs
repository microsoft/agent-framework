// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

internal static partial class Logs
{
    [LoggerMessage(
        EventId = 1,
        Level = LogLevel.Information,
        Message = "[{SessionId}] Request: [{Role}] {Content}")]
    public static partial void LogAgentRequest(
        this ILogger logger,
        AgentSessionId sessionId,
        ChatRole role,
        string content);

    [LoggerMessage(
        EventId = 2,
        Level = LogLevel.Information,
        Message = "[{SessionId}] Response: [{Role}] {Content} (Input tokens: {InputTokenCount}, Output tokens: {OutputTokenCount}, Total tokens: {TotalTokenCount})")]
    public static partial void LogAgentResponse(
        this ILogger logger,
        AgentSessionId sessionId,
        ChatRole role,
        string content,
        long? inputTokenCount,
        long? outputTokenCount,
        long? totalTokenCount);

    [LoggerMessage(
        EventId = 3,
        Level = LogLevel.Information,
        Message = "Signalling agent with session ID '{SessionId}'")]
    public static partial void LogSignallingAgent(this ILogger logger, AgentSessionId sessionId);

    [LoggerMessage(
        EventId = 4,
        Level = LogLevel.Information,
        Message = "Polling agent with session ID '{SessionId}' for response with correlation ID '{CorrelationId}'")]
    public static partial void LogStartPollingForResponse(this ILogger logger, AgentSessionId sessionId, string correlationId);

    [LoggerMessage(
        EventId = 5,
        Level = LogLevel.Information,
        Message = "Found response for agent with session ID '{SessionId}' with correlation ID '{CorrelationId}'")]
    public static partial void LogDonePollingForResponse(this ILogger logger, AgentSessionId sessionId, string correlationId);
}
