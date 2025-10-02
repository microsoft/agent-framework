// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a SuperStep completed.
/// </summary>
/// <param name="stepNumber">The zero-based index of the SuperStep associated with this event.</param>
/// <param name="completionInfo">Debug information about the state of the system on SuperStep completion.</param>
public sealed class SuperStepCompletedEvent(int stepNumber, SuperStepCompletionInfo? completionInfo = null) : SuperStepEvent(stepNumber, data: completionInfo)
{
    /// <summary>
    /// Gets the debug information about the state of the system on SuperStep completion.
    /// </summary>
    public SuperStepCompletionInfo? CompletionInfo => completionInfo;
}
