// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Represents content indicating that an agent step has finished.
/// </summary>
public sealed class StepFinishedContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="StepFinishedContent"/> class.
    /// </summary>
    /// <param name="stepName">The name of the step.</param>
    public StepFinishedContent(string stepName)
    {
        this.StepName = stepName;
    }

    /// <summary>
    /// Gets the name of the step.
    /// </summary>
    public string StepName { get; }
}
