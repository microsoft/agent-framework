// Copyright (c) Microsoft. All rights reserved.

using System;
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

    /// <summary>
    /// Gets or sets the maximum depth to search for script and resource files within each skill directory.
    /// A value of <c>1</c> searches only the skill root directory. A value of <c>2</c> searches the root
    /// and one level of subdirectories.
    /// When <see langword="null"/>, the source uses the default depth of <c>2</c>.
    /// </summary>
    /// <remarks>
    /// Must be greater than or equal to <c>1</c>; lower values are rejected by the constructor.
    /// </remarks>
    public int? SearchDepth { get; set; }

    /// <summary>
    /// Gets or sets a predicate that filters discovered script files.
    /// The predicate receives an <see cref="AgentFileSkillFilterContext"/> containing the skill's name
    /// and the file's path relative to the skill directory.
    /// Return <see langword="true"/> to include the file or <see langword="false"/> to exclude it.
    /// When <see langword="null"/>, all scripts matching the allowed extensions are included.
    /// </summary>
    public Func<AgentFileSkillFilterContext, bool>? ScriptFilter { get; set; }

    /// <summary>
    /// Gets or sets a predicate that filters discovered resource files.
    /// The predicate receives an <see cref="AgentFileSkillFilterContext"/> containing the skill's name
    /// and the file's path relative to the skill directory.
    /// Return <see langword="true"/> to include the file or <see langword="false"/> to exclude it.
    /// When <see langword="null"/>, all resources matching the allowed extensions are included.
    /// </summary>
    public Func<AgentFileSkillFilterContext, bool>? ResourceFilter { get; set; }
}
