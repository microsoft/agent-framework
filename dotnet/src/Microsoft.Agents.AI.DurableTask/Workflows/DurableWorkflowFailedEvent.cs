// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;

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
    public DurableWorkflowFailedEvent(string errorMessage) : base(errorMessage)
    {
        this.ErrorMessage = errorMessage;
    }

    /// <summary>
    /// Gets the error message describing the failure.
    /// </summary>
    public string ErrorMessage { get; }
}
