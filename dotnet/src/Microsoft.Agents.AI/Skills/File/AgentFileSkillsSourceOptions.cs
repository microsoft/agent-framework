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

    /// <summary>
    /// Gets or sets relative folder paths to scan for script files within each skill directory.
    /// Values may be single-segment names (e.g., <c>"scripts"</c>) or multi-segment relative
    /// paths (e.g., <c>"sub/scripts"</c>). Use <c>"."</c> to include files directly at the
    /// skill root. Leading <c>"./"</c> prefixes, trailing separators, and backslashes are
    /// normalized automatically; paths containing <c>".."</c> segments or absolute paths are
    /// rejected.
    /// When <see langword="null"/>, defaults to <c>scripts</c> (per the
    /// <see href="https://agentskills.io/specification">Agent Skills specification</see>).
    /// When set, replaces the defaults entirely.
    /// </summary>
    public IEnumerable<string>? ScriptFolders { get; set; }

    /// <summary>
    /// Gets or sets relative folder paths to scan for resource files within each skill directory.
    /// Values may be single-segment names (e.g., <c>"references"</c>) or multi-segment relative
    /// paths (e.g., <c>"sub/resources"</c>). Use <c>"."</c> to include files directly at the
    /// skill root. Leading <c>"./"</c> prefixes, trailing separators, and backslashes are
    /// normalized automatically; paths containing <c>".."</c> segments or absolute paths are
    /// rejected.
    /// When <see langword="null"/>, defaults to <c>references</c> and <c>assets</c> (per the
    /// <see href="https://agentskills.io/specification">Agent Skills specification</see>).
    /// When set, replaces the defaults entirely.
    /// </summary>
    public IEnumerable<string>? ResourceFolders { get; set; }
}
