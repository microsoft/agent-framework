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

    /// <summary>
    /// Gets or sets the text the caller believes is currently on that line. When set, the edit is
    /// rejected unless it matches, which catches an out-of-date line number or a file that changed
    /// since it was read. This is the line's own text: a numbered read prefixes each line with its
    /// number and a tab, and that prefix is not part of the line. The trailing line terminator is
    /// ignored in the comparison.
    /// </summary>
    [JsonPropertyName("expected_line")]
    [Description("Optional: the text you believe is currently on that line, as reported by grep. Give the line's own text only: a numbered read prefixes each line with its number and a tab, and that prefix is not part of the line. When supplied, the edit is rejected unless it matches, which catches an out-of-date line number or a file that changed since you looked. The trailing newline is ignored in the comparison.")]
    public string? ExpectedLine { get; set; }
}
