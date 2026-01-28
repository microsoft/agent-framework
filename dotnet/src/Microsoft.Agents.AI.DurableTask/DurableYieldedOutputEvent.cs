// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Event raised when an executor yields intermediate output via <see cref="IWorkflowContext.YieldOutputAsync"/>.
/// </summary>
/// <remarks>
/// This is the durable equivalent of <see cref="WorkflowOutputEvent"/> since that class has an internal
/// constructor not accessible from outside the Workflows assembly.
/// </remarks>
public sealed class DurableYieldedOutputEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableYieldedOutputEvent"/> class.
    /// </summary>
    /// <param name="executorId">The ID of the executor that yielded the output.</param>
    /// <param name="output">The yielded output value.</param>
    public DurableYieldedOutputEvent(string executorId, object output) : base(output)
    {
        this.ExecutorId = executorId;
        this.Output = output;
    }

    /// <summary>
    /// Gets the ID of the executor that yielded the output.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// Gets the yielded output value.
    /// </summary>
    public object Output { get; }
}
