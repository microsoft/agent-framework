// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// High-performance logging messages using LoggerMessage source generator for InProcessActorContext.
/// </summary>
internal static partial class Log
{
    // Actor context lifecycle logging
    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor context created: ActorId={ActorId}")]
    public static partial void ActorContextCreated(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor context starting: ActorId={ActorId}")]
    public static partial void ActorContextStarting(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor context started: ActorId={ActorId}")]
    public static partial void ActorContextStarted(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor context disposing: ActorId={ActorId}")]
    public static partial void ActorContextDisposing(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Information,
        Message = "Actor context disposed: ActorId={ActorId}")]
    public static partial void ActorContextDisposed(ILogger logger, string actorId);

    // Message handling logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Message enqueued: ActorId={ActorId}, MessageId={MessageId}, Type={MessageType}")]
    public static partial void MessageEnqueued(ILogger logger, string actorId, string messageId, string messageType);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Message yielded: ActorId={ActorId}, MessageId={MessageId}, Type={MessageType}, Count={MessageCount}")]
    public static partial void MessageYielded(ILogger logger, string actorId, string messageId, string messageType, int messageCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Watch messages started: ActorId={ActorId}")]
    public static partial void WatchMessagesStarted(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Watch messages completed: ActorId={ActorId}, TotalMessages={MessageCount}")]
    public static partial void WatchMessagesCompleted(ILogger logger, string actorId, int messageCount);

    // Request handling logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Send request started: ActorId={ActorId}, MessageId={MessageId}")]
    public static partial void SendRequestStarted(ILogger logger, string actorId, string messageId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Request message created: ActorId={ActorId}, MessageId={MessageId}, Method={Method}")]
    public static partial void RequestMessageCreated(ILogger logger, string actorId, string messageId, string method);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Request message found in inbox: ActorId={ActorId}, MessageId={MessageId}")]
    public static partial void RequestMessageFound(ILogger logger, string actorId, string messageId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Response handle created: ActorId={ActorId}, MessageId={MessageId}")]
    public static partial void ResponseHandleCreated(ILogger logger, string actorId, string messageId);

    // Progress update logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Progress update received: ActorId={ActorId}, MessageId={MessageId}, SequenceNumber={SequenceNumber}")]
    public static partial void ProgressUpdateReceived(ILogger logger, string actorId, string messageId, int sequenceNumber);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Progress update published: ActorId={ActorId}, MessageId={MessageId}")]
    public static partial void ProgressUpdatePublished(ILogger logger, string actorId, string messageId);

    [LoggerMessage(
        Level = LogLevel.Error,
        Message = "Progress update failed: ActorId={ActorId}, MessageId={MessageId}, Reason={Reason}")]
    public static partial void ProgressUpdateFailed(ILogger logger, string actorId, string messageId, string reason);

    // Storage operation logging
    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Read operation started: ActorId={ActorId}, OperationCount={OperationCount}")]
    public static partial void ReadOperationStarted(ILogger logger, string actorId, int operationCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Read operation completed: ActorId={ActorId}, ResultCount={ResultCount}")]
    public static partial void ReadOperationCompleted(ILogger logger, string actorId, int resultCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Write operation started: ActorId={ActorId}, OperationCount={OperationCount}")]
    public static partial void WriteOperationStarted(ILogger logger, string actorId, int operationCount);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Write operation completed: ActorId={ActorId}, Success={Success}")]
    public static partial void WriteOperationCompleted(ILogger logger, string actorId, bool success);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Send request operation encountered: ActorId={ActorId}")]
    public static partial void SendRequestOperationEncountered(ILogger logger, string actorId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Update request operation processing: ActorId={ActorId}, MessageId={MessageId}")]
    public static partial void UpdateRequestOperationProcessing(ILogger logger, string actorId, string messageId);

    [LoggerMessage(
        Level = LogLevel.Debug,
        Message = "Operation processing completed: ActorId={ActorId}, ProcessedCount={ProcessedCount}")]
    public static partial void OperationProcessingCompleted(ILogger logger, string actorId, int processedCount);
}
