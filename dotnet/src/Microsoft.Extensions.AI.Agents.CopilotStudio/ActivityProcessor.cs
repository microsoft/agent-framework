// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.CopilotStudio;

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
                else
                {
                    logger.LogWarning("Unknown activity type '{ActivityType}' received.", activity.Type);
                }
            }
        }
    }

    private static ChatMessage CreateChatMessageFromActivity(IActivity activity, IEnumerable<AIContent> messageContent) =>
        new(ChatRole.Assistant, [.. messageContent])
        {
            AuthorName = activity.From?.Name,
            MessageId = activity.Id,
            RawRepresentation = activity
        };
}
