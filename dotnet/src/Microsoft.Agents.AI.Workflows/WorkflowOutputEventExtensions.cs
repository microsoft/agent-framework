// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Extension helpers for inspecting <see cref="WorkflowOutputEvent"/> tag membership.
/// </summary>
public static class WorkflowOutputEventExtensions
{
    /// <summary>
    /// Returns <see langword="true"/> if the event carries
    /// <see cref="OutputTag.Intermediate"/> in its <see cref="WorkflowOutputEvent.Tags"/>.
    /// </summary>
    public static bool IsIntermediate(this WorkflowOutputEvent evt)
    {
        Throw.IfNull(evt);
        return evt.HasTag(OutputTag.Intermediate);
    }
}
