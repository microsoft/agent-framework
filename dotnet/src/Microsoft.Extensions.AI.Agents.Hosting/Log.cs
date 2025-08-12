// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// High-performance logging messages using LoggerMessage source generator.
/// </summary>
internal static partial class Log
{
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
