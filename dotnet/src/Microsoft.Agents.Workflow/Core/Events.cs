// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// .
/// </summary>
public record WorkflowEvent(object? Data = null);

/// <summary>
/// .
/// </summary>
public record WorkflowStartedEvent : WorkflowEvent;

/// <summary>
/// .
/// </summary>
public record WorkflowCompletedEvent : WorkflowEvent;

/// <summary>
/// .
/// </summary>
public record ExecutorEvent : WorkflowEvent
{
    /// <summary>
    /// The identifier of the executor that generated this event.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// .
    /// </summary>
    public ExecutorEvent(string executorId, object? data = null) : base(data)
    {
        this.ExecutorId = Throw.IfNull(executorId);
    }
}

/// <summary>
/// .
/// </summary>
public record ExecutorInvokeEvent : ExecutorEvent
{
    /// <summary>
    /// .
    /// </summary>
    public ExecutorInvokeEvent(string executorId, object? data = null) : base(executorId, data)
    {
    }
}

/// <summary>
/// .
/// </summary>
public record ExecutorCompleteEvent : ExecutorEvent
{
    /// <summary>
    /// .
    /// </summary>
    public ExecutorCompleteEvent(string executorId, object? data = null) : base(executorId, data) { }
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
