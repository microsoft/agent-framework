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
}
