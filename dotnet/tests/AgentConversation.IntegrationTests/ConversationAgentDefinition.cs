// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace AgentConversation.IntegrationTests;

/// <summary>
/// Defines an agent participating in a <see cref="IConversationTestCase"/>.
/// </summary>
public sealed class ConversationAgentDefinition
{
    /// <summary>
    /// Gets or sets the unique name identifying this agent within the test case.
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// Gets or sets the system instructions for the agent.
    /// </summary>
    public string Instructions { get; init; } = "You are a helpful assistant.";

    /// <summary>
    /// Gets or sets the optional list of tools available to the agent.
    /// </summary>
    public IList<AITool>? Tools { get; init; }
}
