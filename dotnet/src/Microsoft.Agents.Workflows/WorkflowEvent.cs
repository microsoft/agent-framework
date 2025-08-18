// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows;

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
