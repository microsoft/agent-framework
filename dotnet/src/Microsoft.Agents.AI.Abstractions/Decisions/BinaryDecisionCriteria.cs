// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Describes what a true and a false answer to a <see cref="BinaryDecisionQuestion"/> mean, to sharpen the semantic
/// boundary between them.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BinaryDecisionCriteria
{
    /// <summary>Gets or sets a description of what a true answer means.</summary>
    public string? TrueDescription { get; set; }

    /// <summary>Gets or sets a description of what a false answer means.</summary>
    public string? FalseDescription { get; set; }
}
