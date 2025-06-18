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
    public static async IAsyncEnumerable<ChatMessage> ProcessActivityAsync(IAsyncEnumerable<IActivity> activities, ILogger logger)
    {
        await foreach (IActivity activity in activities.ConfigureAwait(false))
        {
            switch (activity.Type)
            {
                case "message":
                    yield return
                        new(ChatRole.Assistant, contents: [.. GetMessageItems(activity)])
                        {
                            RawRepresentation = activity,
                        };
                    break;
                case "typing":
                    yield return
                        new(ChatRole.Assistant, contents: [new TextReasoningContent(activity.Text)])
                        {
                            RawRepresentation = activity,
                        };
                    break;
                case "event":
                    break;
                default:
                    logger.LogWarning("Unknown activity type '{ActivityType}' received.", activity.Type);
                    break;
            }
        }
    }

    private static IEnumerable<AIContent> GetMessageItems(IActivity activity)
    {
        yield return new TextContent(activity.Text);
        foreach (CardAction action in activity.SuggestedActions?.Actions ?? [])
        {
            yield return new TextContent(action.Title);
        }
    }
}
