// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Agents.Core.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.CopilotStudio;

/// <summary>
/// Contains code to process <see cref="IActivity"/> responses from the Copilot Studio agent and convert them to <see cref="ChatMessage"/> objects.
/// </summary>
internal static class ActivityProcessor
{
    public static async IAsyncEnumerable<(ChatMessage message, bool reasoning)> ProcessActivityAsync(IAsyncEnumerable<IActivity> activities, bool streaming, ILogger logger)
    {
        await foreach (IActivity activity in activities.ConfigureAwait(false))
        {
            switch (activity.Type)
            {
                case "message":
                    // For streaming scenarios, we sometimes receive intermediate text via "typing" activities, but not always.
                    // In some cases the respnose is also returned multiple times via "typing" activities, so the only reliable
                    // way to get the final response is to wait for a "message" activity.

                    // TODO: figure out if/how we want to support CardActions publicly on the abstraction.
                    // The activity text doesn't make sense without the actions, as the message
                    // is typically instructing the user to pick from the provided list of actions.
                    yield return (CreateChatMessageFromActivity(activity, [new TextContent(activity.Text)]), false);
                    break;
                case "typing":
                case "event":
                    yield return (CreateChatMessageFromActivity(activity, [new TextReasoningContent(activity.Text)]), true);
                    break;
                default:
                    logger.LogWarning("Unknown activity type '{ActivityType}' received.", activity.Type);
                    break;
            }
        }
    }

    private static ChatMessage CreateChatMessageFromActivity(IActivity activity, IEnumerable<AIContent> messageContent)
    {
        return new ChatMessage(ChatRole.Assistant, [.. messageContent])
        {
            AuthorName = activity.From?.Name,
            MessageId = activity.Id,
            RawRepresentation = activity
        };
    }
}
