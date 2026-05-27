// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="FileMemoryProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileMemoryProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent for using the file memory tools.
    /// </summary>
    /// <value>
    /// When <see langword="null"/> (the default), the provider uses built-in instructions
    /// that guide the agent on how to use file-based memory effectively.
    /// </value>
    public string? Instructions { get; set; }
}
