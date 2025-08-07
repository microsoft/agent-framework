// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Base class for <see cref="Workflow"/>-scoped events.
/// </summary>
public record WorkflowEvent(object? Data = null);

/// <summary>
/// Event triggered when a workflow starts execution.
/// </summary>
public record WorkflowStartedEvent : WorkflowEvent;

/// <summary>
/// Event triggered when a workflow completes execution.
/// </summary>
/// <remarks>
/// The user is expected to raise this event from a terminating <see cref="Executor"/>, or to build
/// the workflow with output capture using <see cref="WorkflowBuilderExtensions.BuildWithOutput"/>.
/// </remarks>
public record WorkflowCompletedEvent : WorkflowEvent;

/// <summary>
/// Event triggered when a workflow executor request external information.
/// </summary>
public record RequestInputEvent(ExternalRequest Request) : WorkflowEvent;

/// <summary>
/// Base class for <see cref="Executor"/>-scoped events.
/// </summary>
public record ExecutorEvent : WorkflowEvent
{
    /// <summary>
    /// The identifier of the executor that generated this event.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="ExecutorEvent"/> class with the specified executor identifier and
    /// optional event data.
    /// </summary>
    /// <param name="executorId">The unique identifier of the executor associated with this event. Cannot be <c>null</c>.</param>
    /// <param name="data">Optional event data to associate with the event. May be <c>null</c> if no additional data is required.</param>
    public ExecutorEvent(string executorId, object? data = null) : base(data)
    {
        this.ExecutorId = Throw.IfNull(executorId);
    }
}

/// <summary>
/// Event triggered when an executor handler is invoked.
/// </summary>
public record ExecutorInvokeEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ExecutorInvokeEvent"/> class.
    /// </summary>
    public ExecutorInvokeEvent(string executorId, object? data = null) : base(executorId, data)
    {
    }
}

/// <summary>
/// Event triggered when an executor handler has completed.
/// </summary>
public record ExecutorCompleteEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ExecutorCompleteEvent"/> class to signal that an executor has
    /// completed its operation.
    /// </summary>
    /// <param name="executorId">The unique identifier of the executor that has completed. Cannot be <c>null</c> or empty.</param>
    /// <param name="result">The result produced by the executor upon completion, or <c>null</c> if no result is available.</param>
    public ExecutorCompleteEvent(string executorId, object? result = null) : base(executorId, result) { }
}

// TODO: This is a placeholder for streaming chat message content.
/// <summary>
/// .
/// </summary>
public class StreamingChatMessageContent
{ }

/// <summary>
/// .
/// </summary>
public record AgentRunStreamingEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunStreamingEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="content"></param>
    public AgentRunStreamingEvent(string executorId, StreamingChatMessageContent? content = null) : base(executorId, data: content)
    {
        this.Content = content;
    }

    /// <summary>
    /// Gets the content of the streaming chat message.
    /// </summary>
    public StreamingChatMessageContent? Content { get; }
}

// TODO: This is a placeholder for non-streaming chat message content.
/// <summary>
/// .
/// </summary>
public class ChatMessageContent
{
}

/// <summary>
/// .
/// </summary>
public record AgentRunEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="content"></param>
    public AgentRunEvent(string executorId, ChatMessageContent? content = null) : base(executorId, data: content)
    {
        this.Content = content;
    }

    /// <summary>
    /// Gets the content of the chat message.
    /// </summary>
    public ChatMessageContent? Content { get; }
}
