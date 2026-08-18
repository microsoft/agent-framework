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
#pragma warning disable VSTHRD200 // The name describes a stream transformation, consistent with the requested pipeline.
    internal static async IAsyncEnumerable<ChatResponseUpdate> MapWorkflowEventsToAGUI(
        this IAsyncEnumerable<ChatResponseUpdate> updates)
    {
        ArgumentNullException.ThrowIfNull(updates);

        await foreach (ChatResponseUpdate update in updates.ConfigureAwait(false))
        {
            switch (update.RawRepresentation)
            {
                case AgentResponseUpdate { RawRepresentation: ExecutorInvokedEvent invoked }:
                    update.RawRepresentation = new StepStartedEvent { StepName = invoked.ExecutorId };
                    yield return update;
                    break;

                case AgentResponseUpdate { RawRepresentation: ExecutorCompletedEvent completed }:
                    update.RawRepresentation = new StepFinishedEvent { StepName = completed.ExecutorId };
                    yield return update;
                    break;

                case AgentResponseUpdate { RawRepresentation: ExecutorFailedEvent failed }:
                    yield return CreateEventUpdate(
                        update,
                        new StepFinishedEvent { StepName = failed.ExecutorId },
                        includeContents: false);
                    yield return update;
                    break;

                default:
                    yield return update;
                    break;
            }
        }
    }
#pragma warning restore VSTHRD200

    private static ChatResponseUpdate CreateEventUpdate(
        ChatResponseUpdate update,
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
