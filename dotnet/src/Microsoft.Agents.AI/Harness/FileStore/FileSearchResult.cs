// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a result from searching files, containing the file name, a content snippet, and matching lines.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSearchResult
{
    /// <summary>
    /// Gets or sets the name of the file that matched the search.
    /// </summary>
    [JsonPropertyName("fileName")]
    public string FileName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets a snippet of content from the file around the first match.
    /// </summary>
    [JsonPropertyName("snippet")]
    public string Snippet { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the lines where matches were found.
    /// </summary>
    [JsonPropertyName("matchingLines")]
    public List<FileSearchMatch> MatchingLines { get; set; } = [];
}
