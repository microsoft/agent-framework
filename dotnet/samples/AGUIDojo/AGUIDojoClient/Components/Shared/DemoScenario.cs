// Copyright (c) Microsoft. All rights reserved.

namespace AGUIDojoClient.Components.Shared;

/// <summary>
/// Represents a demo scenario in the AG-UI dojo.
/// </summary>
/// <param name="Id">Unique identifier for the scenario (e.g., "agentic_chat").</param>
/// <param name="Title">Display title of the scenario.</param>
/// <param name="Description">Brief description of what the scenario demonstrates.</param>
/// <param name="Tags">Collection of tags categorizing the scenario's features.</param>
/// <param name="Endpoint">Server endpoint path for the AG-UI connection.</param>
/// <param name="Icon">Optional emoji icon for the scenario.</param>
public record DemoScenario(
    string Id,
    string Title,
    string Description,
    IReadOnlyList<string> Tags,
    string Endpoint,
    string Icon = "💬"
);
