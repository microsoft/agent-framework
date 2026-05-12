// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the state of the <see cref="FileMemoryProvider"/>,
/// stored in the session's <see cref="AgentSessionStateBag"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileMemoryState
{
    /// <summary>
    /// Gets or sets the working folder path for this session, relative to the store root.
    /// </summary>
    [JsonPropertyName("workingFolder")]
    public string WorkingFolder { get; set; } = string.Empty;
}
