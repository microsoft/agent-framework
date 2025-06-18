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
    public static async IAsyncEnumerable<ChatMessage> ProcessActivityAsync(IAsyncEnumerable<IActivity> activities, bool streaming, ILogger logger)
    {
        await foreach (IActivity activity in activities.ConfigureAwait(false))
        {
            switch (activity.Type)
            {
                case "message":
                    yield return CreateChatMessageFromActivity(activity, GetMessageItems(activity));
                    break;
                case "typing" when streaming:
                    yield return CreateChatMessageFromActivity(activity, [new TextReasoningContent(activity.Text)]);
                    break;
                case "event":
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

    private static IEnumerable<AIContent> GetMessageItems(IActivity activity)
    {
        yield return new TextContent(activity.Text)
        {
            // TODO: figure out if/how we want to support CardActions publicly on the abstraction.
            // The activity text doesn't make sense without the actions, as the message
            // is typically instructing the user to pick from the provided list of actions.
            RawRepresentation = activity,
        };
    }
}
