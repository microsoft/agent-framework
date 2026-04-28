// Copyright (c) Microsoft. All rights reserved.

namespace Aspire.Hosting.AgentFramework;

/// <summary>
/// Describes an AI agent exposed by an agent service backend, used for entity discovery in DevUI.
/// </summary>
/// <remarks>
/// <para>
/// When added via <see cref="AgentFrameworkBuilderExtensions.WithAgentService{TSource}"/>,
/// agent metadata is declared at the AppHost level so that the DevUI aggregator can build the
/// entity listing without querying each backend's <c>/v1/entities</c> endpoint.
/// </para>
/// <para>
/// Agent services only need to expose the standard OpenAI Responses and Conversations API endpoints
/// (<c>MapOpenAIResponses</c> and <c>MapOpenAIConversations</c>), not a custom discovery endpoint.
/// </para>
/// </remarks>
/// <param name="Id">The unique identifier for the agent, typically matching the name passed to <c>AddAIAgent</c>.</param>
/// <param name="Description">A short description of the agent's capabilities.</param>
public record AgentEntityInfo(string Id, string? Description = null)
{
    /// <summary>
    /// Gets the display name for the agent. Defaults to <see cref="Id"/> if not specified.
    /// </summary>
    public string Name { get; init; } = Id;

    /// <summary>
    /// Gets the entity type. Defaults to <c>"agent"</c>.
    /// </summary>
    public string Type { get; init; } = "agent";

    /// <summary>
    /// Gets the framework identifier. Defaults to <c>"agent_framework"</c>.
    /// </summary>
    public string Framework { get; init; } = "agent_framework";
}
