// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Base class for <see cref="Executor"/>-scoped events.
/// </summary>
[JsonDerivedType(typeof(ExecutorInvokedEvent))]
[JsonDerivedType(typeof(ExecutorCompletedEvent))]
[JsonDerivedType(typeof(ExecutorFailedEvent))]
public class ExecutorEvent(string executorId, object? data) : WorkflowEvent(data)
{
    /// <summary>
    /// The identifier of the executor that generated this event.
    /// </summary>
    public string ExecutorId => executorId;

    /// <inheritdoc/>
    public override string ToString() =>
        this.Data is not null ?
            $"{this.GetType().Name}(Executor = {this.ExecutorId}, Data: {this.Data.GetType()} = {this.Data})" :
            $"{this.GetType().Name}(Executor = {this.ExecutorId})";
}
