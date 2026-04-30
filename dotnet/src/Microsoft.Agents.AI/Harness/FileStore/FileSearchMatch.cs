// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a match found within a file during a search operation.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSearchMatch
{
    /// <summary>
    /// Gets or sets the 1-based line number where the match was found.
    /// </summary>
    [JsonPropertyName("lineNumber")]
    public int LineNumber { get; set; }

    /// <summary>
    /// Gets or sets the content of the matching line.
    /// </summary>
    [JsonPropertyName("line")]
    public string Line { get; set; } = string.Empty;
}
