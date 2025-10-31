﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class AgentRunResponseUpdateAGUIExtensions
{
#if !ASPNETCORE
    public static async IAsyncEnumerable<AgentRunResponseUpdate> AsAgentRunResponseUpdatesAsync(
        this IAsyncEnumerable<BaseEvent> events,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? currentMessageId = null;
        ChatRole currentRole = default!;
        string? conversationId = null;
        string? responseId = null;
        await foreach (var evt in events.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            switch (evt)
            {
                case RunStartedEvent runStarted:
                    conversationId = runStarted.ThreadId;
                    responseId = runStarted.RunId;
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [])
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        CreatedAt = DateTimeOffset.UtcNow
                    });
                    break;
                case RunFinishedEvent runFinished:
                    if (!string.Equals(runFinished.ThreadId, conversationId, StringComparison.Ordinal))
                    {
                        throw new InvalidOperationException($"The run finished event didn't match the run started event thread ID: {runFinished.ThreadId}, {conversationId}");
                    }
                    if (!string.Equals(runFinished.RunId, responseId, StringComparison.Ordinal))
                    {
                        throw new InvalidOperationException($"The run finished event didn't match the run started event run ID: {runFinished.RunId}, {responseId}");
                    }
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant, runFinished.Result?.GetRawText())
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        CreatedAt = DateTimeOffset.UtcNow
                    });
                    break;
                case RunErrorEvent runError:
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [(new ErrorContent(runError.Message) { ErrorCode = runError.Code })]));
                    break;
                case TextMessageStartEvent textStart:
                    if (currentRole != default || currentMessageId != null)
                    {
                        throw new InvalidOperationException("Received TextMessageStartEvent while another message is being processed.");
                    }

                    currentRole = AGUIChatMessageExtensions.MapChatRole(textStart.Role);
                    currentMessageId = textStart.MessageId;
                    break;
                case TextMessageContentEvent textContent:
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        currentRole,
                        textContent.Delta)
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        MessageId = textContent.MessageId,
                        CreatedAt = DateTimeOffset.UtcNow
                    });
                    break;
                case TextMessageEndEvent textEnd:
                    if (currentMessageId != textEnd.MessageId)
                    {
                        throw new InvalidOperationException("Received TextMessageEndEvent for a different message than the current one.");
                    }
                    currentRole = default!;
                    currentMessageId = null;
                    break;
            }
        }
    }
#endif

    public static async IAsyncEnumerable<BaseEvent> AsAGUIEventStreamAsync(
        this IAsyncEnumerable<AgentRunResponseUpdate> updates,
        string threadId,
        string runId,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new RunStartedEvent
        {
            ThreadId = threadId,
            RunId = runId
        };

        string? currentMessageId = null;
        await foreach (var update in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            var chatResponse = update.AsChatResponseUpdate();
            if (chatResponse is { Contents.Count: > 0 } && chatResponse.Contents[0] is TextContent && !string.Equals(currentMessageId, chatResponse.MessageId, StringComparison.Ordinal))
            {
                // End the previous message if there was one
                if (currentMessageId is not null)
                {
                    yield return new TextMessageEndEvent
                    {
                        MessageId = currentMessageId
                    };
                }

                // Start the new message
                yield return new TextMessageStartEvent
                {
                    MessageId = chatResponse.MessageId!,
                    Role = chatResponse.Role!.Value.Value
                };

                currentMessageId = chatResponse.MessageId;
            }

            // Emit text content if present
            if (chatResponse is { Contents.Count: > 0 } && chatResponse.Contents[0] is TextContent textContent)
            {
                yield return new TextMessageContentEvent
                {
                    MessageId = chatResponse.MessageId!,
                    Delta = textContent.Text ?? string.Empty
                };
            }
        }

        // End the last message if there was one
        if (currentMessageId is not null)
        {
            yield return new TextMessageEndEvent
            {
                MessageId = currentMessageId
            };
        }

        yield return new RunFinishedEvent
        {
            ThreadId = threadId,
            RunId = runId,
        };
    }
}
