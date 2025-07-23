// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides constants used by actor runtime telemetry services following OpenTelemetry semantic conventions.
/// Extends the base agent telemetry with runtime-specific attributes and operations.
/// </summary>
internal static class ActorRuntimeOpenTelemetryConsts
{
    /// <summary>
    /// The default source name for actor runtime telemetry.
    /// </summary>
    public const string DefaultSourceName = "Microsoft.Extensions.AI.Agents.Runtime";

    /// <summary>
    /// The default source name for in-process actor runtime telemetry.
    /// </summary>
    public const string InProcessSourceName = "Microsoft.Extensions.AI.Agents.Runtime.InProcess";

    /// <summary>
    /// The unit for count measurements.
    /// </summary>
    public const string CountUnit = "count";

    /// <summary>
    /// The unit for byte measurements.
    /// </summary>
    public const string ByteUnit = "byte";

    /// <summary>
    /// Constants for runtime operation names following OpenTelemetry semantic conventions.
    /// These operations align with RPC and GenAI conventions where applicable.
    /// </summary>
    public static class Operations
    {
        /// <summary>
        /// Actor creation operation.
        /// </summary>
        public const string CreateActor = "create_actor";

        /// <summary>
        /// Actor retrieval operation.
        /// </summary>
        public const string GetActor = "get_actor";

        /// <summary>
        /// Actor invocation operation (aligns with GenAI agent invoke conventions).
        /// </summary>
        public const string InvokeActor = "invoke_actor";

        /// <summary>
        /// Actor start operation.
        /// </summary>
        public const string StartActor = "start_actor";

        /// <summary>
        /// Actor stop operation.
        /// </summary>
        public const string StopActor = "stop_actor";

        /// <summary>
        /// Actor dispose operation.
        /// </summary>
        public const string DisposeActor = "dispose_actor";

        /// <summary>
        /// Message send operation.
        /// </summary>
        public const string SendMessage = "send_message";

        /// <summary>
        /// Message receive operation.
        /// </summary>
        public const string ReceiveMessage = "receive_message";

        /// <summary>
        /// Message process operation.
        /// </summary>
        public const string ProcessMessage = "process_message";

        /// <summary>
        /// Request send operation (follows RPC client pattern).
        /// </summary>
        public const string SendRequest = "send_request";

        /// <summary>
        /// Request receive operation (follows RPC server pattern).
        /// </summary>
        public const string ReceiveRequest = "receive_request";

        /// <summary>
        /// Request process operation.
        /// </summary>
        public const string ProcessRequest = "process_request";

        /// <summary>
        /// Response send operation.
        /// </summary>
        public const string SendResponse = "send_response";

        /// <summary>
        /// Response receive operation.
        /// </summary>
        public const string ReceiveResponse = "receive_response";

        /// <summary>
        /// Progress update operation.
        /// </summary>
        public const string ProgressUpdate = "progress_update";

        /// <summary>
        /// State read operation.
        /// </summary>
        public const string StateRead = "state_read";

        /// <summary>
        /// State write operation.
        /// </summary>
        public const string StateWrite = "state_write";

        /// <summary>
        /// Actor runtime initialization operation.
        /// </summary>
        public const string InitializeRuntime = "initialize_runtime";

        /// <summary>
        /// Actor runtime shutdown operation.
        /// </summary>
        public const string ShutdownRuntime = "shutdown_runtime";
    }

    /// <summary>
    /// Constants for span naming patterns following OpenTelemetry semantic conventions.
    /// Span names should be low-cardinality and follow the pattern: {namespace} {operation_name} [{target}]
    /// </summary>
    public static class SpanNames
    {
        /// <summary>
        /// Base pattern for actor operations: "actor {operation}"
        /// </summary>
        public const string ActorOperationPattern = "actor {0}";

        /// <summary>
        /// Pattern for actor operations with specific actor type: "actor {operation} {actor_type}"
        /// </summary>
        public const string ActorOperationWithTypePattern = "actor {0} {1}";

        /// <summary>
        /// Pattern for message operations: "actor.message {operation}"
        /// </summary>
        public const string MessageOperationPattern = "actor.message {0}";

        /// <summary>
        /// Pattern for request operations: "actor.request {operation}"
        /// </summary>
        public const string RequestOperationPattern = "actor.request {0}";

        /// <summary>
        /// Pattern for state operations: "actor.state {operation}"
        /// </summary>
        public const string StateOperationPattern = "actor.state {0}";

        /// <summary>
        /// Pattern for runtime operations: "actor.runtime {operation}"
        /// </summary>
        public const string RuntimeOperationPattern = "actor.runtime {0}";

        /// <summary>
        /// Formats a span name for actor operations.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <returns>Formatted span name</returns>
        public static string FormatActorOperation(string operation) => $"actor {operation}";

        /// <summary>
        /// Formats a span name for actor operations with actor type.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <param name="actorType">The actor type</param>
        /// <returns>Formatted span name</returns>
        public static string FormatActorOperationWithType(string operation, string actorType) => $"actor {operation} {actorType}";

        /// <summary>
        /// Formats a span name for message operations.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <returns>Formatted span name</returns>
        public static string FormatMessageOperation(string operation) => $"actor.message {operation}";

        /// <summary>
        /// Formats a span name for request operations.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <returns>Formatted span name</returns>
        public static string FormatRequestOperation(string operation) => $"actor.request {operation}";

        /// <summary>
        /// Formats a span name for state operations.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <returns>Formatted span name</returns>
        public static string FormatStateOperation(string operation) => $"actor.state {operation}";

        /// <summary>
        /// Formats a span name for runtime operations.
        /// </summary>
        /// <param name="operation">The operation name</param>
        /// <returns>Formatted span name</returns>
        public static string FormatRuntimeOperation(string operation) => $"actor.runtime {operation}";
    }

    /// <summary>
    /// Constants for actor-related telemetry attributes.
    /// </summary>
    public static class Actor
    {
        /// <summary>
        /// The attribute name for the actor ID.
        /// </summary>
        public const string Id = "actor.id";

        /// <summary>
        /// The attribute name for the actor type.
        /// </summary>
        public const string Type = "actor.type";

        /// <summary>
        /// The attribute name for the actor key.
        /// </summary>
        public const string Key = "actor.key";

        /// <summary>
        /// The attribute name for the actor operation.
        /// </summary>
        public const string Operation = "actor.operation";

        /// <summary>
        /// The attribute name for whether the actor exists.
        /// </summary>
        public const string Exists = "actor.exists";

        /// <summary>
        /// The attribute name for whether the actor was started.
        /// </summary>
        public const string Started = "actor.started";

        /// <summary>
        /// The attribute name for the actor runtime type.
        /// </summary>
        public const string RuntimeType = "actor.runtime.type";

        /// <summary>
        /// The attribute name for the actor state.
        /// </summary>
        public const string State = "actor.state";

        /// <summary>
        /// RPC system identifier for actor runtime (follows RPC semantic conventions).
        /// </summary>
        public const string RpcSystem = "rpc.system";

        /// <summary>
        /// RPC service name for actor runtime (follows RPC semantic conventions).
        /// </summary>
        public const string RpcService = "rpc.service";

        /// <summary>
        /// RPC method name for actor runtime (follows RPC semantic conventions).
        /// </summary>
        public const string RpcMethod = "rpc.method";

        /// <summary>
        /// The system name for actor runtime operations.
        /// </summary>
        public const string SystemName = "actor_runtime";

        /// <summary>
        /// Constants for actor lifecycle attributes.
        /// </summary>
        public static class Lifecycle
        {
            /// <summary>
            /// The attribute name for the actor creation time.
            /// </summary>
            public const string CreatedAt = "actor.lifecycle.created_at";

            /// <summary>
            /// The attribute name for the actor start time.
            /// </summary>
            public const string StartedAt = "actor.lifecycle.started_at";

            /// <summary>
            /// The attribute name for the actor stop time.
            /// </summary>
            public const string StoppedAt = "actor.lifecycle.stopped_at";

            /// <summary>
            /// The attribute name for the actor uptime.
            /// </summary>
            public const string Uptime = "actor.lifecycle.uptime";
        }

        /// <summary>
        /// Constants for actor context attributes.
        /// </summary>
        public static class Context
        {
            /// <summary>
            /// The attribute name for the actor context type.
            /// </summary>
            public const string Type = "actor.context.type";

            /// <summary>
            /// The attribute name for the actor context status.
            /// </summary>
            public const string Status = "actor.context.status";

            /// <summary>
            /// The attribute name for the actor context error.
            /// </summary>
            public const string Error = "actor.context.error";
        }

        /// <summary>
        /// Constants for actor performance metrics.
        /// </summary>
        public static class Performance
        {
            /// <summary>
            /// The attribute name for messages processed count.
            /// </summary>
            public const string MessagesProcessed = "actor.performance.messages_processed";

            /// <summary>
            /// The attribute name for requests processed count.
            /// </summary>
            public const string RequestsProcessed = "actor.performance.requests_processed";

            /// <summary>
            /// The attribute name for processing time.
            /// </summary>
            public const string ProcessingTime = "actor.performance.processing_time";

            /// <summary>
            /// The attribute name for queue size.
            /// </summary>
            public const string QueueSize = "actor.performance.queue_size";
        }
    }

    /// <summary>
    /// Constants for message-related telemetry attributes.
    /// </summary>
    public static class Message
    {
        /// <summary>
        /// The attribute name for the message ID.
        /// </summary>
        public const string Id = "message.id";

        /// <summary>
        /// The attribute name for the message type.
        /// </summary>
        public const string Type = "message.type";

        /// <summary>
        /// The attribute name for the message method.
        /// </summary>
        public const string Method = "message.method";

        /// <summary>
        /// The attribute name for the message size in bytes.
        /// </summary>
        public const string Size = "message.size";

        /// <summary>
        /// The attribute name for the message timestamp.
        /// </summary>
        public const string Timestamp = "message.timestamp";

        /// <summary>
        /// The attribute name for the message sender.
        /// </summary>
        public const string Sender = "message.sender";

        /// <summary>
        /// The attribute name for the message recipient.
        /// </summary>
        public const string Recipient = "message.recipient";

        /// <summary>
        /// The attribute name for the message status.
        /// </summary>
        public const string Status = "message.status";

        /// <summary>
        /// The attribute name for the message sequence number.
        /// </summary>
        public const string SequenceNumber = "message.sequence_number";

        /// <summary>
        /// Constants for message processing attributes.
        /// </summary>
        public static class Processing
        {
            /// <summary>
            /// The attribute name for processing start time.
            /// </summary>
            public const string StartTime = "message.processing.start_time";

            /// <summary>
            /// The attribute name for processing end time.
            /// </summary>
            public const string EndTime = "message.processing.end_time";

            /// <summary>
            /// The attribute name for processing duration.
            /// </summary>
            public const string Duration = "message.processing.duration";

            /// <summary>
            /// The attribute name for processing status.
            /// </summary>
            public const string Status = "message.processing.status";

            /// <summary>
            /// The attribute name for processing error.
            /// </summary>
            public const string Error = "message.processing.error";
        }
    }

    /// <summary>
    /// Constants for request-related telemetry attributes.
    /// </summary>
    public static class Request
    {
        /// <summary>
        /// The attribute name for the request ID.
        /// </summary>
        public const string Id = "request.id";

        /// <summary>
        /// The attribute name for the request method.
        /// </summary>
        public const string Method = "request.method";

        /// <summary>
        /// The attribute name for the request status.
        /// </summary>
        public const string Status = "request.status";

        /// <summary>
        /// The attribute name for the request timeout.
        /// </summary>
        public const string Timeout = "request.timeout";

        /// <summary>
        /// The attribute name for whether the request was cancelled.
        /// </summary>
        public const string Cancelled = "request.cancelled";

        /// <summary>
        /// The attribute name for the request retry count.
        /// </summary>
        public const string RetryCount = "request.retry_count";
    }

    /// <summary>
    /// Constants for response-related telemetry attributes.
    /// </summary>
    public static class Response
    {
        /// <summary>
        /// The attribute name for the response ID.
        /// </summary>
        public const string Id = "response.id";

        /// <summary>
        /// The attribute name for the response status.
        /// </summary>
        public const string Status = "response.status";

        /// <summary>
        /// The attribute name for the response size.
        /// </summary>
        public const string Size = "response.size";

        /// <summary>
        /// The attribute name for the response type.
        /// </summary>
        public const string Type = "response.type";
    }

    /// <summary>
    /// Constants for state-related telemetry attributes.
    /// </summary>
    public static class State
    {
        /// <summary>
        /// The attribute name for the state operation type.
        /// </summary>
        public const string OperationType = "state.operation.type";

        /// <summary>
        /// The attribute name for the state operation count.
        /// </summary>
        public const string OperationCount = "state.operation.count";

        /// <summary>
        /// The attribute name for the state result count.
        /// </summary>
        public const string ResultCount = "state.result.count";

        /// <summary>
        /// The attribute name for the state operation success.
        /// </summary>
        public const string Success = "state.success";

        /// <summary>
        /// The attribute name for the state ETag.
        /// </summary>
        public const string ETag = "state.etag";

        /// <summary>
        /// The attribute name for the state size.
        /// </summary>
        public const string Size = "state.size";

        /// <summary>
        /// The attribute name for the state key.
        /// </summary>
        public const string Key = "state.key";
    }

    /// <summary>
    /// Constants for runtime client metrics.
    /// </summary>
    public static class Client
    {
        /// <summary>
        /// Constants for operation duration metrics.
        /// </summary>
        public static class OperationDuration
        {
            /// <summary>
            /// The description for the operation duration metric.
            /// </summary>
            public const string Description = "Measures the duration of actor runtime operations";

            /// <summary>
            /// The name for the operation duration metric.
            /// </summary>
            public const string Name = "actor.runtime.client.operation.duration";

            /// <summary>
            /// The explicit bucket boundaries for the operation duration histogram.
            /// </summary>
            public static readonly double[] ExplicitBucketBoundaries = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0];
        }

        /// <summary>
        /// Constants for message count metrics.
        /// </summary>
        public static class MessageCount
        {
            /// <summary>
            /// The description for the message count metric.
            /// </summary>
            public const string Description = "Measures the number of messages processed by actors";

            /// <summary>
            /// The name for the message count metric.
            /// </summary>
            public const string Name = "actor.runtime.client.message.count";
        }

        /// <summary>
        /// Constants for request count metrics.
        /// </summary>
        public static class RequestCount
        {
            /// <summary>
            /// The description for the request count metric.
            /// </summary>
            public const string Description = "Measures the number of requests processed by actors";

            /// <summary>
            /// The name for the request count metric.
            /// </summary>
            public const string Name = "actor.runtime.client.request.count";
        }

        /// <summary>
        /// Constants for actor count metrics.
        /// </summary>
        public static class ActorCount
        {
            /// <summary>
            /// The description for the actor count metric.
            /// </summary>
            public const string Description = "Measures the number of active actors";

            /// <summary>
            /// The name for the actor count metric.
            /// </summary>
            public const string Name = "actor.runtime.client.actor.count";
        }

        /// <summary>
        /// Constants for queue size metrics.
        /// </summary>
        public static class QueueSize
        {
            /// <summary>
            /// The description for the queue size metric.
            /// </summary>
            public const string Description = "Measures the size of actor message queues";

            /// <summary>
            /// The name for the queue size metric.
            /// </summary>
            public const string Name = "actor.runtime.client.queue.size";

            /// <summary>
            /// The explicit bucket boundaries for the queue size histogram.
            /// </summary>
            public static readonly int[] ExplicitBucketBoundaries = [0, 1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000];
        }

        /// <summary>
        /// Constants for state operation metrics.
        /// </summary>
        public static class StateOperations
        {
            /// <summary>
            /// The description for the state operations metric.
            /// </summary>
            public const string Description = "Measures the number of state operations";

            /// <summary>
            /// The name for the state operations metric.
            /// </summary>
            public const string Name = "actor.runtime.client.state.operations";
        }
    }

    /// <summary>
    /// Constants for error attributes.
    /// </summary>
    public static class ErrorInfo
    {
        /// <summary>
        /// The attribute name for the error type (follows OpenTelemetry error conventions).
        /// </summary>
        public const string Type = "error.type";

        /// <summary>
        /// The attribute name for the error message.
        /// </summary>
        public const string Message = "error.message";

        /// <summary>
        /// The attribute name for the error stack trace.
        /// </summary>
        public const string StackTrace = "error.stack_trace";

        /// <summary>
        /// Well-known error type for unknown errors.
        /// </summary>
        public const string TypeOther = "_OTHER";

        /// <summary>
        /// Well-known error types for actor runtime operations.
        /// </summary>
        public static class Types
        {
            /// <summary>
            /// Actor not found error.
            /// </summary>
            public const string ActorNotFound = "actor_not_found";

            /// <summary>
            /// Actor already exists error.
            /// </summary>
            public const string ActorAlreadyExists = "actor_already_exists";

            /// <summary>
            /// Message delivery failure.
            /// </summary>
            public const string MessageDeliveryFailure = "message_delivery_failure";

            /// <summary>
            /// Request timeout error.
            /// </summary>
            public const string RequestTimeout = "request_timeout";

            /// <summary>
            /// State operation failure.
            /// </summary>
            public const string StateOperationFailure = "state_operation_failure";

            /// <summary>
            /// Runtime initialization failure.
            /// </summary>
            public const string RuntimeInitializationFailure = "runtime_initialization_failure";
        }
    }

    /// <summary>
    /// Constants for event attributes and well-known event names.
    /// </summary>
    public static class EventInfo
    {
        /// <summary>
        /// The attribute name for the event name.
        /// </summary>
        public const string Name = "event.name";

        /// <summary>
        /// The attribute name for the event data.
        /// </summary>
        public const string Data = "event.data";

        /// <summary>
        /// The attribute name for the event timestamp.
        /// </summary>
        public const string Timestamp = "event.timestamp";

        /// <summary>
        /// Well-known event names for actor runtime operations.
        /// </summary>
        public static class Names
        {
            /// <summary>
            /// Actor created event.
            /// </summary>
            public const string ActorCreated = "actor.created";

            /// <summary>
            /// Actor started event.
            /// </summary>
            public const string ActorStarted = "actor.started";

            /// <summary>
            /// Actor stopped event.
            /// </summary>
            public const string ActorStopped = "actor.stopped";

            /// <summary>
            /// Message sent event.
            /// </summary>
            public const string MessageSent = "actor.message.sent";

            /// <summary>
            /// Message received event.
            /// </summary>
            public const string MessageReceived = "actor.message.received";

            /// <summary>
            /// Request completed event.
            /// </summary>
            public const string RequestCompleted = "actor.request.completed";

            /// <summary>
            /// State updated event.
            /// </summary>
            public const string StateUpdated = "actor.state.updated";

            /// <summary>
            /// Runtime initialized event.
            /// </summary>
            public const string RuntimeInitialized = "actor.runtime.initialized";

            /// <summary>
            /// Runtime shutdown event.
            /// </summary>
            public const string RuntimeShutdown = "actor.runtime.shutdown";
        }
    }
}
