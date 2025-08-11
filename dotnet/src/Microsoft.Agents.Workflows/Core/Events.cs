// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Core;

/// <summary>
/// Base class for <see cref="Workflow"/>-scoped events.
/// </summary>
public class WorkflowEvent(object? data = null)
{
    /// <summary>
    /// Optional payload
    /// </summary>
    public object? Data => data;

    /// <inheritdoc/>
    public override string ToString()
    {
        if (this.Data != null)
        {
            return $"{this.GetType().Name}(Data: {this.Data.GetType()} = {this.Data})";
        }

        return $"{this.GetType().Name}()";
    }
}

/// <summary>
/// Event triggered when a workflow starts execution.
/// </summary>
/// <param name="message">The message triggering the start of workflow execution.</param>
public sealed class WorkflowStartedEvent(object? message = null) : WorkflowEvent(data: message);

/// <summary>
/// Event triggered when a workflow completes execution.
/// </summary>
/// <remarks>
/// The user is expected to raise this event from a terminating <see cref="ExecutorBase"/>, or to build
/// the workflow with output capture using <see cref="WorkflowBuilderExtensions.BuildWithOutput"/>.
/// </remarks>
/// <param name="result">The result of the execution of the workflow.</param>
public sealed class WorkflowCompletedEvent(object? result = null) : WorkflowEvent(data: result);

/// <summary>
/// Event triggered when a workflow encounters an error.
/// </summary>
/// <param name="e">
/// Optionally, the <see cref="Exception"/> representing the error.
/// </param>
public sealed class WorkflowErrorEvent(Exception? e) : WorkflowEvent(e);

/// <summary>
/// Event triggered when a workflow encounters a warning-condition.
/// </summary>
/// <param name="message">The warning message.</param>
public sealed class WorkflowWarningEvent(string message) : WorkflowEvent(message);

/// <summary>
/// Event triggered when a workflow executor request external information.
/// </summary>
public sealed class RequestInputEvent(ExternalRequest request) : WorkflowEvent(request)
{
    /// <summary>
    /// The request to be serviced and data payload associated with it.
    /// </summary>
    public ExternalRequest Request => request;
}

/// <summary>
/// Base class for <see cref="ExecutorBase"/>-scoped events.
/// </summary>
public class ExecutorEvent(string executorId, object? data) : WorkflowEvent(data)
{
    /// <summary>
    /// The identifier of the executor that generated this event.
    /// </summary>
    public string ExecutorId => executorId;

    /// <inheritdoc/>
    public override string ToString()
    {
        if (this.Data != null)
        {
            return $"{this.GetType().Name}(Executor = {this.ExecutorId}, Data: {this.Data.GetType()} = {this.Data})";
        }

        return $"{this.GetType().Name}(Executor = {this.ExecutorId})";
    }
}

/// <summary>
/// Event triggered when an executor handler is invoked.
/// </summary>
/// <param name="executorId">The unique identifier of the executor being invoked.</param>
/// <param name="message">The invocation message.</param>
public sealed class ExecutorInvokeEvent(string executorId, object message) : ExecutorEvent(executorId, data: message);

/// <summary>
/// Event triggered when an executor handler has completed.
/// </summary>
/// <param name="executorId">The unique identifier of the executor that has completed.</param>
/// <param name="result">The result produced by the executor upon completion, or <c>null</c> if no result is available.</param>
public sealed class ExecutorCompleteEvent(string executorId, object? result) : ExecutorEvent(executorId, data: result);

/// <summary>
/// Event triggered when an executor handler fails.
/// </summary>
/// <param name="executorId">The unique identifier of the executor that has failed.</param>
/// <param name="err">The exception representing the error.</param>
public sealed class ExecutorFailureEvent(string executorId, Exception? err) : ExecutorEvent(executorId, data: err);

/// <summary>
/// Event triggered when an agent run is completed.
/// </summary>
public class AgentRunEvent : ExecutorEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunEvent"/> class.
    /// </summary>
    /// <param name="executorId">The identifier of the executor that generated this event.</param>
    /// <param name="response"></param>
    public AgentRunEvent(string executorId, AgentRunResponse? response = null) : base(executorId, data: response)
    {
        this.Response = response;
    }

    /// <summary>
    /// Gets the content of the agent response.
    /// </summary>
    public AgentRunResponse? Response { get; }
}
