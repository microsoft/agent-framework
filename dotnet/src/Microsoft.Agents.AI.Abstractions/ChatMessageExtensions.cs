// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Contains extension methods for <see cref="ChatMessage"/>
/// </summary>
public static class ChatMessageExtensions
{
    /// <summary>
    /// Gets the source type of the provided <see cref="ChatMessage"/> in the context of messages passed into an agent run.
    /// </summary>
    /// <param name="message">The <see cref="ChatMessage"/> for which we need the source type.</param>
    /// <returns>An <see cref="AgentRequestMessageSourceType"/> value indicating the source type of the <see cref="ChatMessage"/>. Defaults to <see
    /// cref="AgentRequestMessageSourceType.External"/> if no explicit source is defined.</returns>
    public static AgentRequestMessageSourceType GetAgentRequestMessageSourceType(this ChatMessage message)
    {
        if (message.AdditionalProperties?.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out var attribution) is true
            && attribution is AgentRequestMessageSourceAttribution typedAttribution)
        {
            return typedAttribution.SourceType;
        }

        return AgentRequestMessageSourceType.External;
    }

    /// <summary>
    /// Gets the source id of the provided <see cref="ChatMessage"/> in the context of messages passed into an agent run.
    /// </summary>
    /// <param name="message">The <see cref="ChatMessage"/> for which we need the source id.</param>
    /// <returns>An <see cref="string"/> value indicating the source id of the <see cref="ChatMessage"/>. Defaults to <see langword="null"/>
    /// if no explicit source id is defined.</returns>
    public static string? GetAgentRequestMessageSourceId(this ChatMessage message)
    {
        if (message.AdditionalProperties?.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out var attribution) is true
            && attribution is AgentRequestMessageSourceAttribution typedAttribution)
        {
            return typedAttribution.SourceId;
        }

        return null;
    }

    /// <summary>
    /// Ensure that the provided message is tagged with the provided source type and source id in the context of a specific agent run.
    /// </summary>
    /// <param name="message">The message to tag.</param>
    /// <param name="sourceType">The source type to tag the message with.</param>
    /// <param name="sourceId">The source id to tag the message with.</param>
    /// <returns>The tagged message.</returns>
    /// <remarks>
    /// If the message is already tagged with the provided source type and source id, it is returned as is.
    /// Otherwise, a cloned message is returned with the appropriate tagging in the AdditionalProperties.
    /// </remarks>
    public static ChatMessage WithAgentRequestMessageSource(this ChatMessage message, AgentRequestMessageSourceType sourceType, string? sourceId = null)
    {
        if (message.AdditionalProperties != null
            // Check if the message was already tagged with the required source type and source id
            && message.AdditionalProperties.TryGetValue(AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, out var messageSourceAttribution)
            && messageSourceAttribution is AgentRequestMessageSourceAttribution typedMessageSourceAttribution
            && typedMessageSourceAttribution.SourceType == sourceType
            && typedMessageSourceAttribution.SourceId == sourceId)
        {
            return message;
        }

        message = message.Clone();
        message.AdditionalProperties ??= new();
        message.AdditionalProperties[AgentRequestMessageSourceAttribution.AdditionalPropertiesKey] =
            new AgentRequestMessageSourceAttribution(sourceType, sourceId);
        return message;
    }
}
