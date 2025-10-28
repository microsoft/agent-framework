// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;
internal static class AgentRunResponseUpdateAGUIExtensions
{
    public static async IAsyncEnumerable<AgentRunResponseUpdate> AsChatResponseUpdatesAsync(
        this IAsyncEnumerable<BaseEvent> events,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? currentMessageId = null;
        ChatRole currentRole = default!;
        await foreach (var evt in events.ConfigureAwait(false))
        {
            switch (evt)
            {
                case RunStartedEvent runStarted:
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [new RunStartedContent(runStarted.ThreadId, runStarted.RunId)]));
                    break;
                case RunFinishedEvent runFinished:
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [new RunFinishedContent(
                            runFinished.ThreadId,
                            runFinished.RunId,
                            runFinished.Result)]));
                    break;
                case RunErrorEvent runError:
                    yield return new AgentRunResponseUpdate(new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [new RunErrorContent(runError.Message, runError.Code)]));
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
                        MessageId = textContent.MessageId
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

    public static async IAsyncEnumerable<BaseEvent> AsAGUIEventStream(
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
            if (chatResponse is { Contents.Count: > 0 } && chatResponse.Contents[0] is TextContent text && !string.Equals(currentMessageId, chatResponse.MessageId, StringComparison.Ordinal))
            {
                if (currentMessageId is not null)
                {
                    yield return new TextMessageStartEvent
                    {
                        MessageId = currentMessageId,
                        Role = chatResponse.Role!.Value.Value
                    };
                }

                if (currentMessageId is not null)
                {
                    yield return new TextMessageEndEvent
                    {
                        MessageId = currentMessageId
                    };
                }
                currentMessageId = chatResponse.MessageId;
            }

        }

        yield return new RunFinishedEvent
        {
            ThreadId = threadId,
            RunId = runId,
        };
    }
}
