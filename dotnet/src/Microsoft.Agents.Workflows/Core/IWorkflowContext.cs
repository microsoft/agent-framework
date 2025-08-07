// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Provides services for an <see cref="ExecutorBase"/> during the execution of a workflow.
/// </summary>
public interface IWorkflowContext
{
    /// <summary>
    /// Adds an event to the workflow's output queue. These events will be raised to the caller of the workflow at the
    /// end of the current SuperStep.
    /// </summary>
    /// <param name="workflowEvent">The event to be raised.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask AddEventAsync(WorkflowEvent workflowEvent);

    /// <summary>
    /// Queues a message to be sent to connected executors. The message will be sent during the next SuperStep.
    /// </summary>
    /// <param name="message">The message to be sent.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    ValueTask SendMessageAsync(object message);

    // TODO: State management
}
