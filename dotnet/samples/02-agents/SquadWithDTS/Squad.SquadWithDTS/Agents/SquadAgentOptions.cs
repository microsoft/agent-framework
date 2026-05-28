// Copyright (c) Microsoft. All rights reserved.
namespace Squad.SquadWithDTS.Agents;

/// <summary>
/// Configuration options for <see cref="SquadAgent"/>, bound from the
/// <c>SquadAgent</c> configuration section.
/// </summary>
public sealed class SquadAgentOptions
{
    /// <summary>
    /// Path to the <c>.squad/</c> folder that contains charter YAML files.
    /// When <see langword="null"/> the Copilot SDK discovers the workspace root
    /// by walking up from the current directory.
    /// </summary>
    public string? SquadFolderPath { get; set; }

    /// <summary>
    /// Identifier sent in the <c>x-agent-id</c> header. Defaults to <c>"repo-local-squad"</c>.
    /// </summary>
    public string AgentId { get; set; } = "repo-local-squad";

    /// <summary>
    /// Human-readable display name for the agent. Defaults to <c>"Squad"</c>.
    /// </summary>
    public string AgentName { get; set; } = "Squad";

    /// <summary>
    /// Brief description surfaced in tool registrations and agent metadata.
    /// </summary>
    public string AgentDescription { get; set; } =
        "Squad governance agent — routes work to the right specialist based on charter definitions.";
}
