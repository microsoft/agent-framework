// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for file-based skill sources.
/// </summary>
/// <remarks>
/// Use this class to configure file-based skill discovery without relying on
/// positional constructor or method parameters. New options can be added here
/// without breaking existing callers.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class AgentFileSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets the allowed file extensions for skill resources.
    /// When <see langword="null"/>, defaults to <c>.md</c>, <c>.json</c>, <c>.yaml</c>,
    /// <c>.yml</c>, <c>.csv</c>, <c>.xml</c>, <c>.txt</c>.
    /// </summary>
    public IEnumerable<string>? AllowedResourceExtensions { get; set; }

    /// <summary>
    /// Gets or sets the allowed file extensions for skill scripts.
    /// When <see langword="null"/>, defaults to <c>.py</c>, <c>.js</c>, <c>.sh</c>,
    /// <c>.ps1</c>, <c>.cs</c>, <c>.csx</c>.
    /// </summary>
    public IEnumerable<string>? AllowedScriptExtensions { get; set; }
}
