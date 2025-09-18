// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Base class for SuperStep-scoped events, for example, <see cref="SuperStepCompletedEvent"/>
/// </summary>
[JsonDerivedType(typeof(SuperStepStartedEvent))]
[JsonDerivedType(typeof(SuperStepCompletedEvent))]
public class SuperStepEvent(int stepNumber, object? data = null) : WorkflowEvent(data)
{
    /// <summary>
    /// The zero-based index of the SuperStep associated with this event.
    /// </summary>
    public int StepNumber => stepNumber;

    /// <inheritdoc/>
    public override string ToString() =>
        this.Data is not null ?
            $"{this.GetType().Name}(Step = {this.StepNumber}, Data: {this.Data.GetType()} = {this.Data})" :
            $"{this.GetType().Name}(Step = {this.StepNumber})";
}
