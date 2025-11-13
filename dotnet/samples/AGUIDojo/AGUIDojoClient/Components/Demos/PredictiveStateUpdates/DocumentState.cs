// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace AGUIDojoClient.Components.Demos.PredictiveStateUpdates;

/// <summary>
/// Represents the document state for the Predictive State Updates demo.
/// This model mirrors the server-side DocumentState and is updated via streaming state updates.
/// </summary>
public sealed class DocumentState
{
    /// <summary>
    /// Gets or sets the document content in Markdown format.
    /// </summary>
    [JsonPropertyName("document")]
    public string Document { get; set; } = string.Empty;
}
