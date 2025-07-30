// Copyright (c) Microsoft. All rights reserved.

using static Microsoft.Extensions.AI.Agents.Runtime.ActorRuntimeOpenTelemetryConsts;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Helper methods for setting common telemetry attributes on activities.
/// </summary>
internal static class ActivityExtensions
{
    public const string ActorCreated = ActorRuntimeOpenTelemetryConsts.EventInfo.Names.ActorCreated;
    public const string ActorStarted = ActorRuntimeOpenTelemetryConsts.EventInfo.Names.ActorStarted;
    public const string MessageSent = ActorRuntimeOpenTelemetryConsts.EventInfo.Names.MessageSent;
    public const string MessageReceived = ActorRuntimeOpenTelemetryConsts.EventInfo.Names.MessageReceived;
    public const string RequestCompleted = ActorRuntimeOpenTelemetryConsts.EventInfo.Names.RequestCompleted;

    // Re-export common status values for convenience
    public const string Started = "started";
    public const string Sent = "sent";
    public const string Enqueued = "enqueued";
    public const string Created = "created";
    public const string Found = "found";
    public const string HandleCreated = "handle_created";

    /// <summary>
    /// Sets common actor attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="operation">Optional operation name.</param>
    public static void SetActorAttributes(this System.Diagnostics.Activity? activity, ActorId actorId, string? operation = null)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(ActorRuntimeOpenTelemetryConsts.Actor.Id, actorId.ToString());
        activity.SetTag(ActorRuntimeOpenTelemetryConsts.Actor.Type, actorId.Type.Name);
        activity.SetTag(ActorRuntimeOpenTelemetryConsts.Actor.RpcSystem, ActorRuntimeOpenTelemetryConsts.Actor.SystemName);

        if (!string.IsNullOrEmpty(operation))
        {
            activity.SetTag(ActorRuntimeOpenTelemetryConsts.Actor.Operation, operation);
        }
    }

    /// <summary>
    /// Sets common message attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="messageId">The message ID.</param>
    /// <param name="messageType">Optional message type.</param>
    /// <param name="method">Optional message method.</param>
    public static void SetMessageAttributes(this System.Diagnostics.Activity? activity, string messageId, string? messageType = null, string? method = null)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(Message.Id, messageId);

        if (!string.IsNullOrEmpty(messageType))
        {
            activity.SetTag(Message.Type, messageType);
        }

        if (!string.IsNullOrEmpty(method))
        {
            activity.SetTag(Message.Method, method);
        }
    }

    /// <summary>
    /// Sets common request attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="requestId">The request ID.</param>
    /// <param name="method">Optional request method.</param>
    /// <param name="timeout">Optional timeout value.</param>
    public static void SetRequestAttributes(this System.Diagnostics.Activity? activity, string requestId, string? method = null, System.TimeSpan? timeout = null)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(Request.Id, requestId);

        if (!string.IsNullOrEmpty(method))
        {
            activity.SetTag(Request.Method, method);
        }

        if (timeout.HasValue)
        {
            activity.SetTag(Request.Timeout, timeout.Value.TotalMilliseconds);
        }
    }

    /// <summary>
    /// Sets common state operation attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="operationType">The type of state operation.</param>
    /// <param name="operationCount">Optional count of operations.</param>
    /// <param name="etag">Optional ETag value.</param>
    public static void SetStateAttributes(this System.Diagnostics.Activity? activity, string operationType, int? operationCount = null, string? etag = null)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(State.OperationType, operationType);

        if (operationCount.HasValue)
        {
            activity.SetTag(State.OperationCount, operationCount.Value);
        }

        if (!string.IsNullOrEmpty(etag))
        {
            activity.SetTag(State.ETag, etag);
        }
    }

    /// <summary>
    /// Sets success/failure status on an activity.
    /// </summary>
    /// <param name="activity">The activity to set status on.</param>
    /// <param name="success">Whether the operation was successful.</param>
    /// <param name="errorMessage">Optional error message for failures.</param>
    public static void SetOperationStatus(this System.Diagnostics.Activity? activity, bool success, string? errorMessage = null)
    {
        if (activity == null)
        {
            return;
        }

        if (success)
        {
            activity.SetStatus(System.Diagnostics.ActivityStatusCode.Ok);
        }
        else
        {
            activity.SetStatus(System.Diagnostics.ActivityStatusCode.Error, errorMessage);
        }
    }

    /// <summary>
    /// Sets error attributes on an activity.
    /// </summary>
    /// <param name="activity">The activity to set error attributes on.</param>
    /// <param name="exception">The exception that occurred.</param>
    /// <param name="errorType">Optional custom error type.</param>
    public static void SetErrorAttributes(this System.Diagnostics.Activity? activity, System.Exception exception, string? errorType = null)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(ErrorInfo.Type, errorType ?? exception.GetType().Name);
        activity.SetTag(ErrorInfo.Message, exception.Message);
        activity.SetStatus(System.Diagnostics.ActivityStatusCode.Error, exception.Message);

        // Add exception event
        activity.AddEvent(new System.Diagnostics.ActivityEvent("exception", System.DateTimeOffset.UtcNow, new System.Diagnostics.ActivityTagsCollection
        {
            [ErrorInfo.Type] = errorType ?? exception.GetType().Name,
            [ErrorInfo.Message] = exception.Message,
            [ErrorInfo.StackTrace] = exception.StackTrace
        }));
    }

    /// <summary>
    /// Sets RPC-style attributes for actor operations.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="service">The RPC service name.</param>
    /// <param name="method">The RPC method name.</param>
    public static void SetRpcAttributes(this System.Diagnostics.Activity? activity, string service, string method)
    {
        if (activity == null)
        {
            return;
        }

        activity.SetTag(Actor.RpcSystem, Actor.SystemName);
        activity.SetTag(Actor.RpcService, service);
        activity.SetTag(Actor.RpcMethod, method);
    }

    /// <summary>
    /// Sets up complete telemetry for actor retrieval/creation operations.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="exists">Whether the actor already exists.</param>
    /// <param name="started">Whether the actor was started.</param>
    public static void SetupActorOperation(this System.Diagnostics.Activity? activity, ActorId actorId, bool? exists = null, bool? started = null)
    {
        if (activity == null)
        {
            return;
        }

        SetActorAttributes(activity, actorId);
        SetRpcAttributes(activity, "ActorRuntime", "GetOrCreateActor");

        if (exists.HasValue)
        {
            activity.SetTag(Actor.Exists, exists.Value);
        }

        if (started.HasValue)
        {
            activity.SetTag(Actor.Started, started.Value);
        }
    }

    /// <summary>
    /// Sets up complete telemetry for message operations.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="messageId">The message ID.</param>
    /// <param name="messageType">Optional message type.</param>
    /// <param name="method">Optional message method.</param>
    /// <param name="status">Optional message status.</param>
    public static void SetupMessageOperation(this System.Diagnostics.Activity? activity, ActorId actorId, string messageId, string? messageType = null, string? method = null, string? status = null)
    {
        if (activity == null)
        {
            return;
        }

        SetActorAttributes(activity, actorId);
        SetMessageAttributes(activity, messageId, messageType, method);

        if (!string.IsNullOrEmpty(status))
        {
            activity.SetTag(Message.Status, status);
        }
    }

    /// <summary>
    /// Sets up complete telemetry for request operations.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="requestId">The request ID.</param>
    /// <param name="method">Optional request method.</param>
    /// <param name="service">The RPC service name.</param>
    /// <param name="rpcMethod">The RPC method name.</param>
    /// <param name="timeout">Optional timeout value.</param>
    public static void SetupRequestOperation(this System.Diagnostics.Activity? activity, ActorId actorId, string requestId, string? method = null, string service = "ActorClient", string rpcMethod = "SendRequest", System.TimeSpan? timeout = null)
    {
        if (activity == null)
        {
            return;
        }

        SetActorAttributes(activity, actorId);
        SetRequestAttributes(activity, requestId, method, timeout);
        SetRpcAttributes(activity, service, rpcMethod);
    }

    /// <summary>
    /// Sets up complete telemetry for state operations.
    /// </summary>
    /// <param name="activity">The activity to set attributes on.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="operationType">The type of state operation.</param>
    /// <param name="operationCount">Optional count of operations.</param>
    /// <param name="etag">Optional ETag value.</param>
    public static void SetupStateOperation(this System.Diagnostics.Activity? activity, ActorId actorId, string operationType, int? operationCount = null, string? etag = null)
    {
        if (activity == null)
        {
            return;
        }

        SetActorAttributes(activity, actorId);
        SetStateAttributes(activity, operationType, operationCount, etag);
    }

    /// <summary>
    /// Records successful completion of an operation with optional additional attributes.
    /// </summary>
    /// <param name="activity">The activity to update.</param>
    /// <param name="additionalTags">Optional additional tags to set.</param>
    public static void RecordSuccess(this System.Diagnostics.Activity? activity, params (string key, object? value)[] additionalTags)
    {
        if (activity == null)
        {
            return;
        }

        SetOperationStatus(activity, true);

        foreach (var (key, value) in additionalTags)
        {
            activity.SetTag(key, value);
        }
    }

    /// <summary>
    /// Records failure of an operation with error details.
    /// </summary>
    /// <param name="activity">The activity to update.</param>
    /// <param name="exception">The exception that occurred.</param>
    /// <param name="errorType">Optional custom error type.</param>
    /// <param name="additionalTags">Optional additional tags to set.</param>
    public static void RecordFailure(this System.Diagnostics.Activity? activity, System.Exception exception, string? errorType = null, params (string key, object? value)[] additionalTags)
    {
        if (activity == null)
        {
            return;
        }

        SetErrorAttributes(activity, exception, errorType);

        foreach (var (key, value) in additionalTags)
        {
            activity.SetTag(key, value);
        }
    }

    /// <summary>
    /// Adds an event with common actor context.
    /// </summary>
    /// <param name="activity">The activity to add the event to.</param>
    /// <param name="eventName">The name of the event.</param>
    /// <param name="actorId">The actor ID.</param>
    /// <param name="additionalData">Optional additional event data.</param>
    public static void AddActorEvent(this System.Diagnostics.Activity? activity, string eventName, ActorId actorId, params (string key, object? value)[] additionalData)
    {
        if (activity == null)
        {
            return;
        }

        var tags = new System.Diagnostics.ActivityTagsCollection
        {
            [Actor.Id] = actorId.ToString(),
            [Actor.Type] = actorId.Type.Name
        };

        foreach (var (key, value) in additionalData)
        {
            tags[key] = value;
        }

        activity.AddEvent(new System.Diagnostics.ActivityEvent(eventName, System.DateTimeOffset.UtcNow, tags));
    }

    /// <summary>
    /// Records successful completion and adds an event in a single terse call.
    /// </summary>
    /// <param name="activity">The activity to update.</param>
    /// <param name="eventName">The name of the event to add.</param>
    /// <param name="actorId">The actor ID for the event.</param>
    /// <param name="statusTags">Status tags to set on the activity.</param>
    /// <param name="eventData">Additional event data.</param>
    public static void CompleteWithEvent(this System.Diagnostics.Activity? activity, string eventName, ActorId actorId, (string key, object? value)[] statusTags, params (string key, object? value)[] eventData)
    {
        if (activity == null)
        {
            return;
        }

        RecordSuccess(activity, statusTags);
        AddActorEvent(activity, eventName, actorId, eventData);
    }

    /// <summary>
    /// Complete with event - ultra-terse single-line calls.
    /// </summary>
    public static void Complete(this System.Diagnostics.Activity? activity, string @event, ActorId actor, string status, params (string, object?)[] data) =>
        CompleteWithEvent(activity, @event, actor, [(Request.Status, status)], data);

    /// <summary>
    /// Complete with multiple status tags and event.
    /// </summary>
    public static void Complete(this System.Diagnostics.Activity? activity, string @event, ActorId actor, (string, object?)[] status, params (string, object?)[] data) =>
        CompleteWithEvent(activity, @event, actor, status, data);

    /// <summary>
    /// Record success with single status.
    /// </summary>
    public static void Success(this System.Diagnostics.Activity? activity, string status) =>
        RecordSuccess(activity, (Request.Status, status));

    /// <summary>
    /// Add actor event.
    /// </summary>
    public static void Event(this System.Diagnostics.Activity? activity, string @event, ActorId actor, params (string, object?)[] data) =>
        AddActorEvent(activity, @event, actor, data);

    /// <summary>
    /// Record failure.
    /// </summary>
    public static void Fail(this System.Diagnostics.Activity? activity, System.Exception exception, string? status = null) =>
        RecordFailure(activity, exception, null, status != null ? (Request.Status, status) : default);
}
