// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods for <see cref="ChatMessage"/>
/// </summary>
public static class ChatMessageExtensions
{
    /// <summary>
    /// Gets the source of the provided <see cref="ChatMessage"/> in the context of messages passed into an agent run.
    /// </summary>
    /// <param name="message">The <see cref="ChatMessage"/> for which we need the source.</param>
    /// <returns>An <see cref="AgentRequestMessageSourceType"/> value indicating the source of the <see cref="ChatMessage"/>. Defaults to <see
    /// cref="AgentRequestMessageSourceType.External"/> if no explicit source is defined.</returns>
    public static AgentRequestMessageSourceType GetAgentRequestMessageSource(this ChatMessage message)
    {
        if (message.AdditionalProperties?.TryGetValue(AgentRequestMessageSourceType.AdditionalPropertiesKey, out var source) is true && source is AgentRequestMessageSourceType typedSource)
        {
            return typedSource;
        }

        return AgentRequestMessageSourceType.External;
    }
}
