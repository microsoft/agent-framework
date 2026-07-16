// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a single direct child of a directory in an <see cref="AgentFileStore"/>,
/// returned by <see cref="AgentFileStore.ListChildrenAsync"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileStoreEntry
{
    /// <summary>The <see cref="Type"/> value for a regular file.</summary>
    public const string File = "file";

    /// <summary>The <see cref="Type"/> value for a subdirectory.</summary>
    public const string Directory = "directory";

    /// <summary>
    /// Initializes a new instance of the <see cref="FileStoreEntry"/> class.
    /// </summary>
    public FileStoreEntry()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="FileStoreEntry"/> class.
    /// </summary>
    /// <param name="name">The name of the entry (a single path segment, not a full path).</param>
    /// <param name="type">Either <see cref="File"/> or <see cref="Directory"/>.</param>
    public FileStoreEntry(string name, string type)
    {
        this.Name = name;
        this.Type = type;
    }

    /// <summary>
    /// Gets or sets the name of the entry (a single path segment relative to the listed directory).
    /// </summary>
    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    /// <summary>
    /// Gets or sets the entry type, either <see cref="File"/> or <see cref="Directory"/>.
    /// </summary>
    [JsonPropertyName("type")]
    public string Type { get; set; } = File;
}
