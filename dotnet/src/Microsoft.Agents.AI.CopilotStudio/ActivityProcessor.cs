// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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

    private static ChatMessage CreateChatMessageFromActivity(IActivity activity, IEnumerable<AIContent> messageContent) =>
        new(ChatRole.Assistant, [.. messageContent])
        {
            AdditionalProperties = MapAdditionalProperties(activity),
            AuthorName = activity.From?.Name,
            CreatedAt = activity.Timestamp,
            MessageId = activity.Id,
            RawRepresentation = activity
        };

    private static AdditionalPropertiesDictionary? MapAdditionalProperties(IActivity activity)
    {
        IDictionary<string, JsonElement>? properties = activity.Properties;
        if (properties is null || properties.Count == 0)
        {
            return null;
        }

        var additionalProperties = new AdditionalPropertiesDictionary();
        foreach (KeyValuePair<string, JsonElement> property in properties)
        {
            additionalProperties[property.Key] = property.Value;
        }

        return additionalProperties;
    }
}
