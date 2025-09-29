// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a workflow encounters an error.
/// </summary>
/// <param name="subworkflowId">The ID of the subworkflow that encountered the error.</param>
/// <param name="e">Optionally, the <see cref="Exception"/> representing the error.</param>
public sealed class SubworkflowErrorEvent(string subworkflowId, Exception? e) : WorkflowErrorEvent(e)
{
    /// <summary>
    /// Gets the ID of the subworkflow that encountered the error.
    /// </summary>
    public string SubworkflowId { get; } = subworkflowId;
}
