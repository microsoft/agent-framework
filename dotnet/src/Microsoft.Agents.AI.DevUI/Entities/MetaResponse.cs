// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DevUI.Entities;

/// <summary>
/// Server metadata response for the /meta endpoint.
/// Provides information about the DevUI server configuration, capabilities, and requirements.
/// </summary>
/// <remarks>
/// This response is used by the frontend to:
/// - Determine the UI mode (developer vs user interface)
/// - Check server capabilities (tracing, OpenAI proxy support)
/// - Verify authentication requirements
/// - Display framework and version information
/// </remarks>
internal sealed record MetaResponse
{
    /// <summary>
    /// Gets the UI interface mode.
    /// "developer" shows debug tools and advanced features, "user" shows a simplified interface.
    /// </summary>
    [JsonPropertyName("ui_mode")]
    public string UiMode { get; init; } = "developer";

    /// <summary>
    /// Gets the DevUI version string.
    /// </summary>
    [JsonPropertyName("version")]
    public string Version { get; init; } = "0.1.0";

    /// <summary>
    /// Gets the backend framework identifier.
    /// Always "agent_framework" for Agent Framework implementations.
    /// </summary>
    [JsonPropertyName("framework")]
    public string Framework { get; init; } = "agent_framework";

    /// <summary>
    /// Gets the backend runtime/language.
    /// "dotnet" for .NET implementations, "python" for Python implementations.
    /// Used by frontend for deployment guides and feature availability.
    /// </summary>
    [JsonPropertyName("runtime")]
    public string Runtime { get; init; } = "dotnet";

    /// <summary>
    /// Gets the server capabilities dictionary.
    /// Key-value pairs indicating which optional features are enabled.
    /// </summary>
    /// <remarks>
    /// Standard capability keys:
    /// - "tracing": Whether trace events are emitted for debugging
    /// - "openai_proxy": Whether the server can proxy requests to OpenAI
    /// </remarks>
    [JsonPropertyName("capabilities")]
    public Dictionary<string, bool> Capabilities { get; init; } = new();

    /// <summary>
    /// Gets a value indicating whether Bearer token authentication is required for API access.
    /// When true, clients must include "Authorization: Bearer {token}" header in requests.
    /// </summary>
    [JsonPropertyName("auth_required")]
    public bool AuthRequired { get; init; }
}
