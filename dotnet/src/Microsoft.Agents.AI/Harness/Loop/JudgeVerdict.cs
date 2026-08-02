// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the structured verdict returned by the judge chat client used by <see cref="AIJudgeLoopEvaluator"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class JudgeVerdict
{
    /// <summary>
    /// Gets or sets a value indicating whether the agent has fully addressed the user's original request.
    /// </summary>
    [Description("True if the agent has fully addressed the original request, otherwise false.")]
    public bool Answered { get; set; }

    /// <summary>
    /// Gets or sets an explanation of what is still missing when the request has not been fully addressed.
    /// </summary>
    [Description("When 'answered' is false, explain what is still missing or what work remains to fully address the original request.")]
    public string GapAnalysis { get; set; } = string.Empty;
}
