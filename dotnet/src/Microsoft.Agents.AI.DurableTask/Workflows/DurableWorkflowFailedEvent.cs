// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Event raised when a durable workflow fails.
/// </summary>
[DebuggerDisplay("Failed: {ErrorMessage}")]
public sealed class DurableWorkflowFailedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowFailedEvent"/> class.
    /// </summary>
    /// <param name="errorMessage">The error message describing the failure.</param>
    /// <param name="failureDetails">The full failure details from the Durable Task runtime, if available.</param>
    public DurableWorkflowFailedEvent(string errorMessage, TaskFailureDetails? failureDetails = null) : base(errorMessage)
    {
        this.ErrorMessage = errorMessage;
        this.FailureDetails = failureDetails;
    }

    /// <summary>
    /// Gets the error message describing the failure.
    /// </summary>
    public string ErrorMessage { get; }

    /// <summary>
    /// Gets the full failure details from the Durable Task runtime, including error type, stack trace, and inner failure.
    /// </summary>
    public TaskFailureDetails? FailureDetails { get; }
}
