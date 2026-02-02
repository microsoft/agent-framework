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

    [LoggerMessage(
        EventId = 6,
        Level = LogLevel.Information,
        Message = "[{SessionId}] TTL expiration time updated to {ExpirationTime:O}")]
    public static partial void LogTTLExpirationTimeUpdated(
        this ILogger logger,
        AgentSessionId sessionId,
        DateTime expirationTime);

    [LoggerMessage(
        EventId = 7,
        Level = LogLevel.Information,
        Message = "[{SessionId}] TTL deletion signal scheduled for {ScheduledTime:O}")]
    public static partial void LogTTLDeletionScheduled(
        this ILogger logger,
        AgentSessionId sessionId,
        DateTime scheduledTime);

    [LoggerMessage(
        EventId = 8,
        Level = LogLevel.Information,
        Message = "[{SessionId}] TTL deletion check running. Expiration time: {ExpirationTime:O}, Current time: {CurrentTime:O}")]
    public static partial void LogTTLDeletionCheck(
        this ILogger logger,
        AgentSessionId sessionId,
        DateTime? expirationTime,
        DateTime currentTime);

    [LoggerMessage(
        EventId = 9,
        Level = LogLevel.Information,
        Message = "[{SessionId}] Entity expired and deleted due to TTL. Expiration time: {ExpirationTime:O}")]
    public static partial void LogTTLEntityExpired(
        this ILogger logger,
        AgentSessionId sessionId,
        DateTime expirationTime);

    [LoggerMessage(
        EventId = 10,
        Level = LogLevel.Information,
        Message = "[{SessionId}] TTL deletion signal rescheduled for {ScheduledTime:O}")]
    public static partial void LogTTLRescheduled(
        this ILogger logger,
        AgentSessionId sessionId,
        DateTime scheduledTime);

    [LoggerMessage(
        EventId = 11,
        Level = LogLevel.Information,
        Message = "[{SessionId}] TTL expiration time cleared (TTL disabled)")]
    public static partial void LogTTLExpirationTimeCleared(
        this ILogger logger,
        AgentSessionId sessionId);

    // Durable workflow logs (EventIds 100-199)

    [LoggerMessage(
        EventId = 100,
        Level = LogLevel.Information,
        Message = "Starting workflow '{WorkflowName}' with instance '{InstanceId}'")]
    public static partial void LogWorkflowStarting(
        this ILogger logger,
        string workflowName,
        string instanceId);

    [LoggerMessage(
        EventId = 101,
        Level = LogLevel.Information,
        Message = "Superstep {Step}: {Count} active executor(s)")]
    public static partial void LogSuperstepStarting(
        this ILogger logger,
        int step,
        int count);

    [LoggerMessage(
        EventId = 102,
        Level = LogLevel.Debug,
        Message = "Superstep {Step} executors: [{Executors}]")]
    public static partial void LogSuperstepExecutors(
        this ILogger logger,
        int step,
        string executors);

    [LoggerMessage(
        EventId = 103,
        Level = LogLevel.Information,
        Message = "Workflow completed")]
    public static partial void LogWorkflowCompleted(
        this ILogger logger);

    [LoggerMessage(
        EventId = 104,
        Level = LogLevel.Debug,
        Message = "Fan-In executor {ExecutorId}: aggregated {Count} messages from [{Sources}]")]
    public static partial void LogFanInAggregated(
        this ILogger logger,
        string executorId,
        int count,
        string sources);

    [LoggerMessage(
        EventId = 105,
        Level = LogLevel.Debug,
        Message = "Executor '{ExecutorId}' returned result (length: {Length}, messages: {MessageCount})")]
    public static partial void LogExecutorResultReceived(
        this ILogger logger,
        string executorId,
        int length,
        int messageCount);

    [LoggerMessage(
        EventId = 106,
        Level = LogLevel.Debug,
        Message = "Dispatching executor '{ExecutorId}' (agentic: {IsAgentic})")]
    public static partial void LogDispatchingExecutor(
        this ILogger logger,
        string executorId,
        bool isAgentic);

    [LoggerMessage(
        EventId = 107,
        Level = LogLevel.Warning,
        Message = "Agent '{AgentName}' not found")]
    public static partial void LogAgentNotFound(
        this ILogger logger,
        string agentName);
}
