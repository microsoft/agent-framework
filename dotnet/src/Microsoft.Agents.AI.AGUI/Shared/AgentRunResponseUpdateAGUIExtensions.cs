// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
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
    public static async IAsyncEnumerable<ChatResponseUpdate> AsChatResponseUpdatesAsync(
        this IAsyncEnumerable<BaseEvent> events,
        JsonSerializerOptions jsonSerializerOptions,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? currentMessageId = null;
        ChatRole currentRole = default!;
        string? conversationId = null;
        string? responseId = null;
        string? currentToolCallId = null;
        string? currentToolCallName = null;
        StringBuilder? accumulatedArgs = null;
        string? currentToolCallParentMessageId = null;
        await foreach (var evt in events.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            switch (evt)
            {
                case RunStartedEvent runStarted:
                    conversationId = runStarted.ThreadId;
                    responseId = runStarted.RunId;
                    yield return new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [])
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        CreatedAt = DateTimeOffset.UtcNow
                    };
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
                    yield return new ChatResponseUpdate(
                        ChatRole.Assistant, runFinished.Result?.GetRawText())
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        CreatedAt = DateTimeOffset.UtcNow
                    };
                    break;
                case RunErrorEvent runError:
                    yield return new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [(new ErrorContent(runError.Message) { ErrorCode = runError.Code })]);
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
                    yield return new ChatResponseUpdate(
                        currentRole,
                        textContent.Delta)
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        MessageId = textContent.MessageId,
                        CreatedAt = DateTimeOffset.UtcNow
                    };
                    break;
                case TextMessageEndEvent textEnd:
                    if (currentMessageId != textEnd.MessageId)
                    {
                        throw new InvalidOperationException("Received TextMessageEndEvent for a different message than the current one.");
                    }
                    currentRole = default!;
                    currentMessageId = null;
                    break;
                case ToolCallStartEvent toolCallStart:
                    if (currentToolCallId != null)
                    {
                        throw new InvalidOperationException("Received ToolCallStartEvent while another tool call is being processed.");
                    }
                    currentToolCallId = toolCallStart.ToolCallId;
                    currentToolCallName = toolCallStart.ToolCallName;
                    currentToolCallParentMessageId = toolCallStart.ParentMessageId;
                    accumulatedArgs = new StringBuilder();
                    break;
                case ToolCallArgsEvent toolCallArgs:
                    if (currentToolCallId != toolCallArgs.ToolCallId)
                    {
                        throw new InvalidOperationException("Received ToolCallArgsEvent for a different tool call than the current one.");
                    }
                    accumulatedArgs!.Append(toolCallArgs.Delta);
                    break;
                case ToolCallEndEvent toolCallEnd:
                    if (currentToolCallId != toolCallEnd.ToolCallId)
                    {
                        throw new InvalidOperationException("Received ToolCallEndEvent for a different tool call than the current one.");
                    }

                    string argsJson = accumulatedArgs!.ToString();
                    IDictionary<string, object?>? arguments = null;
                    if (!string.IsNullOrEmpty(argsJson))
                    {
                        var typeInfo = jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)) as JsonTypeInfo<IDictionary<string, object?>>;
                        arguments = JsonSerializer.Deserialize(argsJson, typeInfo!);
                    }

                    var functionCallContent = new FunctionCallContent(
                        currentToolCallId!,
                        currentToolCallName!,
                        arguments);

                    yield return new ChatResponseUpdate(
                        ChatRole.Assistant,
                        [functionCallContent])
                    {
                        ConversationId = conversationId,
                        ResponseId = responseId,
                        MessageId = currentToolCallParentMessageId,
                        CreatedAt = DateTimeOffset.UtcNow
                    };

                    currentToolCallId = null;
                    currentToolCallName = null;
                    accumulatedArgs = null;
                    currentToolCallParentMessageId = null;
                    break;
            }
        }
    }

    /// <summary>
    /// Converts AGUI BaseEvent stream to AgentRunResponseUpdate stream (wrapper for backward compatibility).
    /// </summary>
    public static async IAsyncEnumerable<AgentRunResponseUpdate> AsAgentRunResponseUpdatesAsync(
        this IAsyncEnumerable<BaseEvent> events,
        JsonSerializerOptions jsonSerializerOptions,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        await foreach (var chatResponseUpdate in events.AsChatResponseUpdatesAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return new AgentRunResponseUpdate(chatResponseUpdate);
        }
    }
#endif

    public static async IAsyncEnumerable<BaseEvent> AsAGUIEventStreamAsync(
        this IAsyncEnumerable<ChatResponseUpdate> updates,
        string threadId,
        string runId,
        JsonSerializerOptions jsonSerializerOptions,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        yield return new RunStartedEvent
        {
            ThreadId = threadId,
            RunId = runId
        };

        string? currentMessageId = null;
        await foreach (var chatResponse in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
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

            // Emit tool call events
            if (chatResponse is { Contents.Count: > 0 })
            {
                foreach (var content in chatResponse.Contents)
                {
                    if (content is FunctionCallContent functionCallContent)
                    {
                        yield return new ToolCallStartEvent
                        {
                            ToolCallId = functionCallContent.CallId,
                            ToolCallName = functionCallContent.Name,
                            ParentMessageId = chatResponse.MessageId
                        };

                        string argumentsJson = JsonSerializer.Serialize(
                            functionCallContent.Arguments,
                            jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)));

                        yield return new ToolCallArgsEvent
                        {
                            ToolCallId = functionCallContent.CallId,
                            Delta = argumentsJson
                        };

                        yield return new ToolCallEndEvent
                        {
                            ToolCallId = functionCallContent.CallId
                        };
                    }
                }
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

    /// <summary>
    /// Converts AgentRunResponseUpdate stream to AGUI BaseEvent stream (wrapper for backward compatibility).
    /// </summary>
    public static async IAsyncEnumerable<BaseEvent> AsAGUIEventStreamAsync(
        this IAsyncEnumerable<AgentRunResponseUpdate> updates,
        string threadId,
        string runId,
        JsonSerializerOptions jsonSerializerOptions,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        async IAsyncEnumerable<ChatResponseUpdate> ConvertToChatAsync([EnumeratorCancellation] CancellationToken ct = default)
        {
            await foreach (var update in updates.WithCancellation(ct).ConfigureAwait(false))
            {
                yield return update.AsChatResponseUpdate();
            }
        }

        await foreach (var evt in ConvertToChatAsync(cancellationToken).AsAGUIEventStreamAsync(threadId, runId, jsonSerializerOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return evt;
        }
    }
}
