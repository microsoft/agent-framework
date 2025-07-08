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
    public static async IAsyncEnumerable<(ChatMessage message, bool reasoning)> ProcessActivityAsync(IAsyncEnumerable<IActivity> activities, bool streaming, ILogger logger)
    {
        await foreach (IActivity activity in activities.ConfigureAwait(false))
        {
            switch (activity.Type)
            {
                case "message":
                    // For streaming scenarios, we sometimes receive intermediate text via "typing" activities, but not always.
                    // In some cases the response is also returned multiple times via "typing" activities, so the only reliable
                    // way to get the final response is to wait for a "message" activity.

                    // TODO: Prototype a custom AIContent type for CardActions, where the user is instructed to
                    // pick from a list of actions.
                    // The activity text doesn't make sense without the actions, as the message
                    // is often instructing the user to pick from the provided list of actions.
                    yield return (CreateChatMessageFromActivity(activity, [new TextContent(activity.Text)]), false);
                    break;
                case "typing":
                case "event":
                    // TODO: Revisit usage of TextReasoningContent here, to evaluate whether all are really reasoning
                    // or whether simply an AIContent base type would be more appropriate.
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
