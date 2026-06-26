// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace AgentConversation.IntegrationTests;

/// <summary>
/// Represents a single step within a <see cref="IConversationTestCase"/>, combining the agent to invoke,
/// an optional input message, and an optional validation delegate.
/// </summary>
public sealed class ConversationStep
{
    /// <summary>
    /// Gets or sets the name of the agent to invoke for this step.
    /// Must match a key in <see cref="IConversationTestCase.AgentDefinitions"/>.
    /// </summary>
    public required string AgentName { get; init; }

    /// <summary>
    /// Gets or sets the optional input message to send to the agent.
    /// When <see langword="null"/>, the agent is invoked with no new user input (useful for
    /// eliciting a response from the existing conversation context).
    /// </summary>
    public ChatMessage? Input { get; init; }

    /// <summary>
    /// Gets or sets an optional delegate that validates the agent response and metrics for this step.
    /// When <see langword="null"/>, no validation is performed.
    /// </summary>
    public Action<AgentResponse, ConversationMetricsReport>? Validate { get; init; }
}
