// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Event raised when a durable workflow completes successfully.
/// </summary>
[DebuggerDisplay("Completed: {Result}")]
public sealed class DurableWorkflowCompletedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowCompletedEvent"/> class.
    /// </summary>
    /// <param name="result">The serialized result of the workflow.</param>
    public DurableWorkflowCompletedEvent(string? result) : base(result)
    {
        this.Result = result;
    }

    /// <summary>
    /// Gets the serialized result of the workflow.
    /// </summary>
    public string? Result { get; }
}
