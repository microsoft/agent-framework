// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a single whole-line replacement used by the file access and file memory
/// <c>replace_lines</c> tools.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileLineEdit
{
    /// <summary>
    /// Gets or sets the 1-based line number to replace.
    /// </summary>
    [JsonPropertyName("line_number")]
    [Description("1-based line number to replace.")]
    public int LineNumber { get; set; }

    /// <summary>
    /// Gets or sets the literal replacement text for the line, including any trailing newline to keep.
    /// An empty string deletes the line entirely (its content and its line break).
    /// </summary>
    [JsonPropertyName("new_line")]
    [Description("Literal replacement text for the line, including any trailing newline you want to keep (the editor does not add one). Set to an empty string to delete the line entirely, including its line break.")]
    public string NewLine { get; set; } = string.Empty;
}
