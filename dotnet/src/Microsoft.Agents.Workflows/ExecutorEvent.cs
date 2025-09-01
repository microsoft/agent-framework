// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Base class for <see cref="Executor"/>-scoped events.
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
