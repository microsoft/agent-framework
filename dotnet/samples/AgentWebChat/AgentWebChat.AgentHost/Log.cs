// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Runtime;

namespace AgentWebChat.AgentHost;

/// <summary>
/// High-performance logging messages using LoggerMessage source generator.
/// </summary>
internal static partial class Log
{
    // API endpoint logging
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor invocation started: Name={ActorName}, SessionId={SessionId}, RequestId={RequestId}, Stream={StreamRequested}")]
    public static partial void ActorInvocationStarted(ILogger logger, string actorName, string sessionId, string requestId, bool streamRequested);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor invocation completed: Name={ActorName}, SessionId={SessionId}, RequestId={RequestId}, Status={Status}, Duration={DurationMs}ms")]
    public static partial void ActorInvocationCompleted(ILogger logger, string actorName, string sessionId, string requestId, RequestStatus status, long durationMs);

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Actor invocation failed: Name={ActorName}, SessionId={SessionId}, RequestId={RequestId}, Duration={DurationMs}ms")]
    public static partial void ActorInvocationFailed(ILogger logger, Exception exception, string actorName, string sessionId, string requestId, long durationMs);

    // SSE streaming logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "SSE streaming started for request: {RequestId}")]
    public static partial void SseStreamingStarted(ILogger logger, string requestId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "SSE progress update sent: RequestId={RequestId}, UpdateCount={UpdateCount}")]
    public static partial void SseProgressUpdateSent(ILogger logger, string requestId, int updateCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "SSE streaming completed: RequestId={RequestId}, TotalUpdates={TotalUpdates}")]
    public static partial void SseStreamingCompleted(ILogger logger, string requestId, int totalUpdates);

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "SSE streaming cancelled: RequestId={RequestId}")]
    public static partial void SseStreamingCanceled(ILogger logger, string requestId);

    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "SSE streaming error: RequestId={RequestId}")]
    public static partial void SseStreamingError(ILogger logger, Exception exception, string requestId);

    // Response processing logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Processing actor response: RequestId={RequestId}, Status={Status}, IsStreaming={IsStreaming}")]
    public static partial void ProcessingActorResponse(ILogger logger, string requestId, RequestStatus status, bool isStreaming);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor response processed successfully: RequestId={RequestId}, ResponseType={ResponseType}")]
    public static partial void ActorResponseProcessed(ILogger logger, string requestId, string responseType);

    // Request/Response logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Actor request received: RequestId={RequestId}, PayloadSize={PayloadSize} bytes, Stream={StreamRequested}")]
    public static partial void ActorRequestReceived(ILogger logger, string requestId, int payloadSize, bool streamRequested);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Actor request sent to runtime: RequestId={RequestId}, ActorName={ActorName}, SessionId={SessionId}")]
    public static partial void ActorRequestSent(ILogger logger, string requestId, string actorName, string sessionId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Actor response handle obtained: RequestId={RequestId}, HasImmediateResponse={HasImmediateResponse}")]
    public static partial void ActorResponseHandleObtained(ILogger logger, string requestId, bool hasImmediateResponse);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Waiting for actor response: RequestId={RequestId}")]
    public static partial void WaitingForActorResponse(ILogger logger, string requestId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Actor response received: RequestId={RequestId}, Status={Status}")]
    public static partial void ActorResponseReceived(ILogger logger, string requestId, RequestStatus status);

    // ChatClientAgentActor logging
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor started: ActorId={ActorId}, AgentName={AgentName}")]
    public static partial void ActorStarted(ILogger logger, string actorId, string agentName);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Thread state restored: ActorId={ActorId}, HasExistingThread={HasExistingThread}")]
    public static partial void ThreadStateRestored(ILogger logger, string actorId, bool hasExistingThread);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Processing agent request: RequestId={RequestId}, ActorId={ActorId}, MessageCount={MessageCount}")]
    public static partial void ProcessingAgentRequest(ILogger logger, string requestId, string actorId, int messageCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Agent streaming update: RequestId={RequestId}, UpdateNumber={UpdateNumber}")]
    public static partial void AgentStreamingUpdate(ILogger logger, string requestId, int updateNumber);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Agent request completed: RequestId={RequestId}, TotalUpdates={TotalUpdates}")]
    public static partial void AgentRequestCompleted(ILogger logger, string requestId, int totalUpdates);

    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "Agent request failed: RequestId={RequestId}, ActorId={ActorId}")]
    public static partial void AgentRequestFailed(ILogger logger, Exception exception, string requestId, string actorId);

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Unknown message type received: MessageType={MessageType}, ActorId={ActorId}")]
    public static partial void UnknownMessageType(ILogger logger, string messageType, string actorId);

    [LoggerMessage(
        Level = LogLevel.Warning,
        Message = "Error processing messages: ActorId={ActorId}")]
    public static partial void ErrorProcessingMessages(ILogger logger, Exception exception, string actorId);

    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "Write operation failed: ActorId={ActorId}, RequestId={RequestId}")]
    public static partial void WriteOperationFailed(ILogger logger, string actorId, string requestId);
}
