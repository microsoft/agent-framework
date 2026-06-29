// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.CopilotStudio;

/// <summary>
/// Contains code to process <see cref="IActivity"/> responses from the Copilot Studio agent and convert them to <see cref="ChatMessage"/> objects.
/// </summary>
internal static class ActivityProcessor
{
    /// <summary>
    /// Processes Copilot Studio activities and yields the corresponding <see cref="ChatMessage"/> instances.
    /// </summary>
    /// <param name="activities">The activities returned by the Copilot Studio client.</param>
    /// <param name="streaming">A value indicating whether the response is being processed in streaming mode.</param>
    /// <param name="logger">The logger used to record processing warnings.</param>
    /// <returns>An asynchronous sequence of <see cref="ChatMessage"/> objects.</returns>
    public static async IAsyncEnumerable<ChatMessage> ProcessActivityAsync(IAsyncEnumerable<IActivity> activities, bool streaming, ILogger logger)
    {
        await foreach (IActivity activity in activities.ConfigureAwait(false))
        {
            // TODO: Prototype a custom AIContent type for CardActions, where the user is instructed to
            // pick from a list of actions.
            // The activity text doesn't make sense without the actions, as the message
            // is often instructing the user to pick from the provided list of actions.
            if (!string.IsNullOrWhiteSpace(activity.Text))
            {
                if ((activity.Type == "message" && !streaming) || (activity.Type == "typing" && streaming))
                {
                    yield return CreateChatMessageFromActivity(activity, [new TextContent(activity.Text)]);
                }
                else if (logger.IsEnabled(LogLevel.Warning))
                {
                    logger.LogWarning("Unknown activity type '{ActivityType}' received.", activity.Type);
                }
            }
        }
    }

    /// <summary>
    /// Creates an <see cref="AgentResponse"/> from processed messages and the last source activity.
    /// </summary>
    /// <param name="agentId">The identifier of the agent that produced the response.</param>
    /// <param name="messages">The response messages produced by the agent.</param>
    /// <param name="lastActivity">The last underlying activity, when available.</param>
    /// <returns>An <see cref="AgentResponse"/> with populated metadata.</returns>
    internal static AgentResponse CreateAgentResponse(string agentId, IList<ChatMessage> messages, IActivity? lastActivity)
    {
        ChatMessage? lastMessage = messages.LastOrDefault();

        DateTimeOffset? createdAt = lastMessage?.CreatedAt;
        if (createdAt is null && lastActivity is not null)
        {
            createdAt = ResolveActivityCreatedAt(lastActivity);
        }

        AdditionalPropertiesDictionary? additionalProperties = lastMessage?.AdditionalProperties;
        if (additionalProperties is null && lastActivity is not null)
        {
            additionalProperties = ResolveActivityAdditionalProperties(lastActivity);
        }

        return new AgentResponse(messages)
        {
            AgentId = agentId,
            ResponseId = lastMessage?.MessageId,
            CreatedAt = createdAt,
            FinishReason = messages.Count > 0 ? ChatFinishReason.Stop : null,
            RawRepresentation = lastActivity,
            AdditionalProperties = additionalProperties,
        };
    }

    /// <summary>
    /// Creates an <see cref="AgentResponseUpdate"/> from a processed <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="agentId">The identifier of the agent that produced the update.</param>
    /// <param name="message">The chat message represented by the update.</param>
    /// <param name="isTerminalUpdate">A value indicating whether this is the final update in the stream.</param>
    /// <returns>An <see cref="AgentResponseUpdate"/> with populated metadata.</returns>
    internal static AgentResponseUpdate CreateAgentResponseUpdate(string agentId, ChatMessage message, bool isTerminalUpdate)
    {
        return new AgentResponseUpdate(message.Role, message.Contents)
        {
            AgentId = agentId,
            AdditionalProperties = message.AdditionalProperties,
            AuthorName = message.AuthorName,
            RawRepresentation = message.RawRepresentation,
            ResponseId = message.MessageId,
            MessageId = message.MessageId,
            CreatedAt = message.CreatedAt,
            FinishReason = isTerminalUpdate ? ChatFinishReason.Stop : null,
        };
    }

    private static ChatMessage CreateChatMessageFromActivity(IActivity activity, IEnumerable<AIContent> messageContent)
    {
        return new(ChatRole.Assistant, [.. messageContent])
        {
            AuthorName = activity.From?.Name,
            MessageId = activity.Id,
            CreatedAt = ResolveActivityCreatedAt(activity),
            AdditionalProperties = ResolveActivityAdditionalProperties(activity),
            RawRepresentation = activity,
        };
    }

    private static DateTimeOffset? ResolveActivityCreatedAt(IActivity activity)
    {
        return activity.Timestamp ?? activity.LocalTimestamp;
    }

    private static AdditionalPropertiesDictionary? ResolveActivityAdditionalProperties(IActivity activity)
    {
        if (activity.Properties is not { Count: > 0 } properties)
        {
            return null;
        }

        AdditionalPropertiesDictionary additionalProperties = new();
        foreach (KeyValuePair<string, JsonElement> property in properties)
        {
            additionalProperties[property.Key] = property.Value;
        }

        return additionalProperties;
    }
}
