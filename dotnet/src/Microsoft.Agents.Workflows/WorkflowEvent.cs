// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Base class for <see cref="Workflow"/>-scoped events.
/// </summary>
[JsonDerivedType(typeof(ExecutorEvent))]
[JsonDerivedType(typeof(SuperStepEvent))]
[JsonDerivedType(typeof(WorkflowStartedEvent))]
[JsonDerivedType(typeof(WorkflowCompletedEvent))]
[JsonDerivedType(typeof(WorkflowErrorEvent))]
[JsonDerivedType(typeof(WorkflowWarningEvent))]
[JsonDerivedType(typeof(RequestInfoEvent))]
public class WorkflowEvent(object? data = null)
{
    /// <summary>
    /// Optional payload
    /// </summary>
    public object? Data => data;

    /// <inheritdoc/>
    public override string ToString() =>
        this.Data is not null ?
            $"{this.GetType().Name}(Data: {this.Data.GetType()} = {this.Data})" :
            $"{this.GetType().Name}()";
}
