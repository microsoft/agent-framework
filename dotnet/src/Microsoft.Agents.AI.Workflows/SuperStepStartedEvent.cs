// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Event triggered when a SuperStep started.
/// </summary>
/// <param name="stepNumber">The zero-based index of the SuperStep associated with this event.</param>
/// <param name="startInfo">Debug information about the state of the system on SuperStep start.</param>
public sealed class SuperStepStartedEvent(int stepNumber, SuperStepStartInfo? startInfo = null) : SuperStepEvent(stepNumber, data: startInfo)
{
    /// <summary>
    /// Gets the debug information about the state of the system on SuperStep start.
    /// </summary>
    public SuperStepStartInfo? StartInfo => startInfo;
}
