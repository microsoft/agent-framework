// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a file entry returned by the <see cref="FileMemoryProvider"/> list files tool,
/// containing the file name and an optional description.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileListEntry
{
    /// <summary>
    /// Gets or sets the name of the file.
    /// </summary>
    [JsonPropertyName("fileName")]
    public string FileName { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the description of the file, or <see langword="null"/> if no description is available.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }
}
