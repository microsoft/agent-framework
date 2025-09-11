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
