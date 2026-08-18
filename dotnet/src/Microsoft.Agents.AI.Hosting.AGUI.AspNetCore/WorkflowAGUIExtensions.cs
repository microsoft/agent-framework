// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using AGUI.Abstractions;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

internal static class WorkflowAGUIExtensions
{
    internal static async IAsyncEnumerable<ChatResponseUpdate> AsAGUIChatResponseUpdatesAsync(
        this IAsyncEnumerable<AgentResponseUpdate> updates)
    {
        ArgumentNullException.ThrowIfNull(updates);

        await foreach (AgentResponseUpdate update in updates.ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case ExecutorInvokedEvent invoked:
                    yield return CreateEventUpdate(
                        update,
                        new StepStartedEvent { StepName = invoked.ExecutorId });
                    break;

                case ExecutorCompletedEvent completed:
                    yield return CreateEventUpdate(
                        update,
                        new StepFinishedEvent { StepName = completed.ExecutorId });
                    break;

                case ExecutorFailedEvent failed:
                    yield return CreateEventUpdate(
                        update,
                        new StepFinishedEvent { StepName = failed.ExecutorId },
                        includeContents: false);
                    yield return update.AsChatResponseUpdate();
                    break;

                default:
                    yield return update.AsChatResponseUpdate();
                    break;
            }
        }
    }

    private static ChatResponseUpdate CreateEventUpdate(
        AgentResponseUpdate update,
        BaseEvent evt,
        bool includeContents = true)
        => new()
        {
            AdditionalProperties = update.AdditionalProperties,
            AuthorName = update.AuthorName,
            Contents = includeContents ? update.Contents : [],
            CreatedAt = update.CreatedAt,
            FinishReason = update.FinishReason,
            MessageId = update.MessageId,
            RawRepresentation = evt,
            ResponseId = update.ResponseId,
            Role = update.Role,
            ContinuationToken = update.ContinuationToken,
        };
}
