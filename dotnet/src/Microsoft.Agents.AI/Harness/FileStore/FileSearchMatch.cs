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
    /// Gets or sets the matching line, verbatim.
    /// </summary>
    /// <remarks>
    /// Implementers should report the line exactly as it appears in the file, keeping its own terminator
    /// (<c>\r\n</c>, <c>\n</c>, or a lone <c>\r</c>), except on a final line that the content does not
    /// terminate. Together with <see cref="LineNumber"/> addressing the same lines the line-edit tools use,
    /// that makes the value reusable as a literal replacement line without re-reading the file.
    /// </remarks>
    [JsonPropertyName("line")]
    public string Line { get; set; } = string.Empty;
}
