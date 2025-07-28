// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.Agents.Orchestration.Workflows.Core;

/// <summary>
/// Provides services for <see cref="Executor"/> subclasses.
/// </summary>
public interface IExecutionContext
{
    /// <summary>
    /// Send a message from the executor to the context.
    /// </summary>
    /// <param name="sourceId">The id of the sender of the message.</param>
    /// <param name="message">The message to be sent.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask SendMessageAsync(string sourceId, object message);

    /// <summary>
    /// Drain all messages from the context.
    /// </summary>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation, containing
    /// a dictionary mapping executor IDs to lists of messages.</returns>
    ValueTask<Dictionary<string, List<object>>> DrainMessagesAsync();

    /// <summary>
    /// Check if there are any message in the context.
    /// </summary>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation, containing
    /// <c>true</c> if there are messages. <c>false</c> if there are not.</returns>
    ValueTask<bool> HasMessagesAsync();

    /// <summary>
    /// Add an event to the execution context.
    /// </summary>
    /// <param name="workflowEvent">The event to be added.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);

    /// <summary>
    /// Drain all events from the context.
    /// </summary>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation, containing
    /// a list of all events.</returns>
    ValueTask<List<WorkflowEvent>> DrainEventsAsync();

    /// <summary>
    /// Check if there are any events in the context.
    /// </summary>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation, containing
    /// <c>true</c> if there are events. <c>false</c> if there are not.</returns>
    ValueTask<bool> HasEventsAsync();
}
