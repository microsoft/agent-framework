// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a constant for the key used to store the source of the agent request message.
/// </summary>
public static class AgentRequestMessageSource
{
    /// <summary>
    /// Provides the key used in <see cref="ChatMessage.AdditionalProperties"/> to store the source of the agent request message.
    /// </summary>
    public static readonly string AdditionalPropertiesKey = "Agent.RequestMessageSource";
}
