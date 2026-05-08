// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal static class ChatResponseUpdateAGUIExtensions
{
    private static readonly MediaTypeHeaderValue? s_jsonPatchMediaType = new("application/json-patch+json");
    private static readonly MediaTypeHeaderValue? s_json = new("application/json");

    public static async IAsyncEnumerable<ChatResponseUpdate> AsChatResponseUpdatesAsync(
        this IAsyncEnumerable<BaseEvent> events,
        JsonSerializerOptions jsonSerializerOptions,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? conversationId = null;
        string? responseId = null;
        var textMessageBuilder = new TextMessageBuilder();
        var toolCallAccumulator = new ToolCallBuilder();
        var reasoningBuilder = new ReasoningMessageBuilder();
        await foreach (var evt in events.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            switch (evt)
            {
                // Lifecycle events
                case RunStartedEvent runStarted:
                    conversationId = runStarted.ThreadId;
                    responseId = runStarted.RunId;
                    toolCallAccumulator.SetConversationAndResponseIds(conversationId, responseId);
                    textMessageBuilder.SetConversationAndResponseIds(conversationId, responseId);
                    reasoningBuilder.SetConversationAndResponseIds(conversationId, responseId);
                    yield return ValidateAndEmitRunStart(runStarted);
                    break;
                case RunFinishedEvent runFinished:
                    yield return ValidateAndEmitRunFinished(conversationId, responseId, runFinished);
                    break;
                case RunErrorEvent runError:
                    yield return new ChatResponseUpdate(ChatRole.Assistant, [(new ErrorContent(runError.Message) { ErrorCode = runError.Code })]);
                    break;

                // Text events
                case TextMessageStartEvent textStart:
                    textMessageBuilder.AddTextStart(textStart);
                    break;
                case TextMessageContentEvent textContent:
                    yield return textMessageBuilder.EmitTextUpdate(textContent);
                    break;
                case TextMessageEndEvent textEnd:
                    textMessageBuilder.EndCurrentMessage(textEnd);
                    break;

                // Tool call events
                case ToolCallStartEvent toolCallStart:
                    toolCallAccumulator.AddToolCallStart(toolCallStart);
                    break;
                case ToolCallArgsEvent toolCallArgs:
                    toolCallAccumulator.AddToolCallArgs(toolCallArgs, jsonSerializerOptions);
                    break;
                case ToolCallEndEvent toolCallEnd:
                    yield return toolCallAccumulator.EmitToolCallUpdate(toolCallEnd, jsonSerializerOptions);
                    break;
                case ToolCallResultEvent toolCallResult:
                    yield return toolCallAccumulator.EmitToolCallResult(toolCallResult, jsonSerializerOptions);
                    break;

                // State snapshot events
                case StateSnapshotEvent stateSnapshot:
                    if (stateSnapshot.Snapshot.HasValue)
                    {
                        yield return CreateStateSnapshotUpdate(stateSnapshot, conversationId, responseId, jsonSerializerOptions);
                    }
                    break;
                case StateDeltaEvent stateDelta:
                    if (stateDelta.Delta.HasValue)
                    {
                        yield return CreateStateDeltaUpdate(stateDelta, conversationId, responseId, jsonSerializerOptions);
                    }
                    break;

                // Reasoning events (explicit lifecycle form)
                case ReasoningMessageStartEvent reasoningStart:
                    reasoningBuilder.AddReasoningStart(reasoningStart);
                    break;
                case ReasoningMessageContentEvent reasoningContent:
                    yield return reasoningBuilder.EmitReasoningContent(reasoningContent);
                    break;
                case ReasoningMessageEndEvent reasoningEnd:
                    reasoningBuilder.EndCurrentMessage(reasoningEnd);
                    break;

                // Reasoning events (chunk shorthand form)
                case ReasoningMessageChunkEvent reasoningChunk:
                    var chunkUpdate = reasoningBuilder.EmitReasoningChunk(reasoningChunk);
                    if (chunkUpdate is not null)
                    {
                        yield return chunkUpdate;
                    }
                    break;

                // Encrypted reasoning value (emitted by either form)
                case ReasoningEncryptedValueEvent encryptedValue:
                    yield return reasoningBuilder.EmitEncryptedValue(encryptedValue);
                    break;

                // ReasoningStartEvent and ReasoningEndEvent are bracket markers only — no content to emit
                case ReasoningStartEvent:
                case ReasoningEndEvent:
                    break;
            }
        }
    }

    private static ChatResponseUpdate CreateStateSnapshotUpdate(
        StateSnapshotEvent stateSnapshot,
        string? conversationId,
        string? responseId,
        JsonSerializerOptions jsonSerializerOptions)
    {
        // Serialize JsonElement directly to UTF-8 bytes using AOT-safe overload
        byte[] jsonBytes = JsonSerializer.SerializeToUtf8Bytes(
            stateSnapshot.Snapshot!.Value,
            jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)));
        DataContent dataContent = new(jsonBytes, "application/json");

        return new ChatResponseUpdate(ChatRole.Assistant, [dataContent])
        {
            ConversationId = conversationId,
            ResponseId = responseId,
            CreatedAt = DateTimeOffset.UtcNow,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["is_state_snapshot"] = true
            }
        };
    }

    private static ChatResponseUpdate CreateStateDeltaUpdate(
        StateDeltaEvent stateDelta,
        string? conversationId,
        string? responseId,
        JsonSerializerOptions jsonSerializerOptions)
    {
        // Serialize JsonElement directly to UTF-8 bytes using AOT-safe overload
        byte[] jsonBytes = JsonSerializer.SerializeToUtf8Bytes(
            stateDelta.Delta!.Value,
            jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)));
        DataContent dataContent = new(jsonBytes, "application/json-patch+json");

        return new ChatResponseUpdate(ChatRole.Assistant, [dataContent])
        {
            ConversationId = conversationId,
            ResponseId = responseId,
            CreatedAt = DateTimeOffset.UtcNow,
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["is_state_delta"] = true
            }
        };
    }

    private sealed class TextMessageBuilder()
    {
        private ChatRole _currentRole;
        private string? _currentMessageId;
        private string? _conversationId;
        private string? _responseId;

        public void SetConversationAndResponseIds(string? conversationId, string? responseId)
        {
            this._conversationId = conversationId;
            this._responseId = responseId;
        }

        public void AddTextStart(TextMessageStartEvent textStart)
        {
            if (this._currentRole != default || this._currentMessageId != null)
            {
                throw new InvalidOperationException("Received TextMessageStartEvent while another message is being processed.");
            }

            this._currentRole = AGUIChatMessageExtensions.MapChatRole(textStart.Role);
            this._currentMessageId = textStart.MessageId;
        }

        internal ChatResponseUpdate EmitTextUpdate(TextMessageContentEvent textContent)
        {
            return new ChatResponseUpdate(
                this._currentRole,
                textContent.Delta)
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = textContent.MessageId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        internal void EndCurrentMessage(TextMessageEndEvent textEnd)
        {
            if (this._currentMessageId != textEnd.MessageId)
            {
                throw new InvalidOperationException("Received TextMessageEndEvent for a different message than the current one.");
            }
            this._currentRole = default;
            this._currentMessageId = null;
        }
    }

    private static ChatResponseUpdate ValidateAndEmitRunStart(RunStartedEvent runStarted)
    {
        return new ChatResponseUpdate(
            ChatRole.Assistant,
            [])
        {
            ConversationId = runStarted.ThreadId,
            ResponseId = runStarted.RunId,
            CreatedAt = DateTimeOffset.UtcNow
        };
    }

    private static ChatResponseUpdate ValidateAndEmitRunFinished(string? conversationId, string? responseId, RunFinishedEvent runFinished)
    {
        if (!string.Equals(runFinished.ThreadId, conversationId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"The run finished event didn't match the run started event thread ID: {runFinished.ThreadId}, {conversationId}");
        }
        if (!string.Equals(runFinished.RunId, responseId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"The run finished event didn't match the run started event run ID: {runFinished.RunId}, {responseId}");
        }

        return new ChatResponseUpdate(
            ChatRole.Assistant, runFinished.Result?.GetRawText())
        {
            ConversationId = conversationId,
            ResponseId = responseId,
            CreatedAt = DateTimeOffset.UtcNow
        };
    }

    private sealed class ToolCallBuilder
    {
        private string? _conversationId;
        private string? _responseId;
        private StringBuilder? _accumulatedArgs;
        private FunctionCallContent? _currentFunctionCall;

        public void AddToolCallStart(ToolCallStartEvent toolCallStart)
        {
            if (this._currentFunctionCall != null)
            {
                throw new InvalidOperationException("Received ToolCallStartEvent while another tool call is being processed.");
            }
            this._accumulatedArgs ??= new StringBuilder();
            this._currentFunctionCall = new(
                    toolCallStart.ToolCallId,
                    toolCallStart.ToolCallName,
                    null);
        }

        public void AddToolCallArgs(ToolCallArgsEvent toolCallArgs, JsonSerializerOptions options)
        {
            if (this._currentFunctionCall == null)
            {
                throw new InvalidOperationException("Received ToolCallArgsEvent without a current tool call.");
            }

            if (!string.Equals(this._currentFunctionCall.CallId, toolCallArgs.ToolCallId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Received ToolCallArgsEvent for a different tool call than the current one.");
            }

            Debug.Assert(this._accumulatedArgs != null, "Accumulated args should have been initialized in ToolCallStartEvent.");
            this._accumulatedArgs.Append(toolCallArgs.Delta);
        }

        internal ChatResponseUpdate EmitToolCallUpdate(ToolCallEndEvent toolCallEnd, JsonSerializerOptions jsonSerializerOptions)
        {
            if (this._currentFunctionCall == null)
            {
                throw new InvalidOperationException("Received ToolCallEndEvent without a current tool call.");
            }
            if (!string.Equals(this._currentFunctionCall.CallId, toolCallEnd.ToolCallId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Received ToolCallEndEvent for a different tool call than the current one.");
            }
            Debug.Assert(this._accumulatedArgs != null, "Accumulated args should have been initialized in ToolCallStartEvent.");
            var arguments = DeserializeArgumentsIfAvailable(this._accumulatedArgs.ToString(), jsonSerializerOptions);
            this._accumulatedArgs.Clear();
            this._currentFunctionCall.Arguments = arguments;
            var invocation = this._currentFunctionCall;
            this._currentFunctionCall = null;
            return new ChatResponseUpdate(
                ChatRole.Assistant,
                [invocation])
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = invocation.CallId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        public ChatResponseUpdate EmitToolCallResult(ToolCallResultEvent toolCallResult, JsonSerializerOptions options)
        {
            return new ChatResponseUpdate(
                ChatRole.Tool,
                [new FunctionResultContent(
                    toolCallResult.ToolCallId,
                    DeserializeResultIfAvailable(toolCallResult, options))])
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = toolCallResult.MessageId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        internal void SetConversationAndResponseIds(string conversationId, string responseId)
        {
            this._conversationId = conversationId;
            this._responseId = responseId;
        }
    }

    private sealed class ReasoningMessageBuilder()
    {
        private string? _currentMessageId;
        private string? _conversationId;
        private string? _responseId;

        public void SetConversationAndResponseIds(string? conversationId, string? responseId)
        {
            this._conversationId = conversationId;
            this._responseId = responseId;
        }

        public void AddReasoningStart(ReasoningMessageStartEvent reasoningStart)
        {
            if (this._currentMessageId != null)
            {
                throw new InvalidOperationException(
                    "Received ReasoningMessageStartEvent while another message is being processed.");
            }

            this._currentMessageId = reasoningStart.MessageId;
        }

        public ChatResponseUpdate EmitReasoningContent(ReasoningMessageContentEvent contentEvent)
        {
            return new ChatResponseUpdate(ChatRole.Assistant, [new TextReasoningContent(contentEvent.Delta)])
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = contentEvent.MessageId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        public ChatResponseUpdate? EmitReasoningChunk(ReasoningMessageChunkEvent chunkEvent)
        {
            if (string.IsNullOrEmpty(chunkEvent.Delta))
            {
                // Empty delta is the implicit close signal for chunk-based streaming
                this._currentMessageId = null;
                return null;
            }

            this._currentMessageId ??= chunkEvent.MessageId;
            return new ChatResponseUpdate(ChatRole.Assistant, [new TextReasoningContent(chunkEvent.Delta)])
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = chunkEvent.MessageId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        public ChatResponseUpdate EmitEncryptedValue(ReasoningEncryptedValueEvent encryptedEvent)
        {
            return new ChatResponseUpdate(ChatRole.Assistant, [new TextReasoningContent("") { ProtectedData = encryptedEvent.EncryptedValue }])
            {
                ConversationId = this._conversationId,
                ResponseId = this._responseId,
                MessageId = encryptedEvent.EntityId,
                CreatedAt = DateTimeOffset.UtcNow
            };
        }

        public void EndCurrentMessage(ReasoningMessageEndEvent reasoningEnd)
        {
            if (!string.Equals(this._currentMessageId, reasoningEnd.MessageId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "Received ReasoningMessageEndEvent for a different message than the current one.");
            }
            this._currentMessageId = null;
        }
    }

    private static IDictionary<string, object?>? DeserializeArgumentsIfAvailable(string argsJson, JsonSerializerOptions options)
    {
        if (!string.IsNullOrEmpty(argsJson))
        {
            return (IDictionary<string, object?>?)JsonSerializer.Deserialize(
                argsJson,
                options.GetTypeInfo(typeof(IDictionary<string, object?>)));
        }

        return null;
    }

    private static object? DeserializeResultIfAvailable(ToolCallResultEvent toolCallResult, JsonSerializerOptions options)
    {
        if (!string.IsNullOrEmpty(toolCallResult.Content))
        {
            return JsonSerializer.Deserialize(toolCallResult.Content, options.GetTypeInfo(typeof(JsonElement)));
        }

        return null;
    }

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
        string? streamingMessageId = null;
        string? currentReasoningBaseId = null;
        string? currentReasoningId = null;
        string? currentReasoningMessageId = null;
        await foreach (var chatResponse in updates.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            // Generate a fallback MessageId when the provider doesn't supply one.
            // This ensures all AGUI events have a valid messageId regardless of agent type.
            if (string.IsNullOrWhiteSpace(chatResponse.MessageId))
            {
                streamingMessageId ??= Guid.NewGuid().ToString("N");
                chatResponse.MessageId = streamingMessageId;
            }

            if (chatResponse is { Contents.Count: > 0 } &&
                chatResponse.Contents[0] is TextContent &&
                !string.Equals(currentMessageId, chatResponse.MessageId, StringComparison.Ordinal))
            {
                // Close any open reasoning block before opening a text message, so AG-UI
                // events are properly bracketed. MEAI providers share one MessageId across
                // reasoning and text content, so the reasoning-block state alone wouldn't
                // detect the transition.
                if (currentReasoningMessageId is not null)
                {
                    yield return new ReasoningMessageEndEvent
                    {
                        MessageId = currentReasoningMessageId
                    };
                    yield return new ReasoningEndEvent
                    {
                        MessageId = currentReasoningId!
                    };
                    currentReasoningBaseId = null;
                    currentReasoningId = null;
                    currentReasoningMessageId = null;
                }

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
            if (chatResponse is { Contents.Count: > 0 } && chatResponse.Contents[0] is TextContent textContent &&
                !string.IsNullOrEmpty(textContent.Text))
            {
                yield return new TextMessageContentEvent
                {
                    MessageId = currentMessageId!,
                    Delta = textContent.Text
                };
            }

            // Emit tool call events and tool result events
            if (chatResponse is { Contents.Count: > 0 })
            {
                foreach (var content in chatResponse.Contents)
                {
                    if (content is FunctionCallContent functionCallContent)
                    {
                        // Close any open reasoning block before emitting tool events.
                        if (currentReasoningMessageId is not null)
                        {
                            yield return new ReasoningMessageEndEvent
                            {
                                MessageId = currentReasoningMessageId
                            };
                            yield return new ReasoningEndEvent
                            {
                                MessageId = currentReasoningId!
                            };
                            currentReasoningBaseId = null;
                            currentReasoningId = null;
                            currentReasoningMessageId = null;
                        }

                        yield return new ToolCallStartEvent
                        {
                            ToolCallId = functionCallContent.CallId,
                            ToolCallName = functionCallContent.Name,
                            ParentMessageId = chatResponse.MessageId
                        };

                        yield return new ToolCallArgsEvent
                        {
                            ToolCallId = functionCallContent.CallId,
                            Delta = JsonSerializer.Serialize(
                                functionCallContent.Arguments,
                                jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object?>)))
                        };

                        yield return new ToolCallEndEvent
                        {
                            ToolCallId = functionCallContent.CallId
                        };
                    }
                    else if (content is FunctionResultContent functionResultContent)
                    {
                        // Close any open reasoning block before emitting tool result events.
                        if (currentReasoningMessageId is not null)
                        {
                            yield return new ReasoningMessageEndEvent
                            {
                                MessageId = currentReasoningMessageId
                            };
                            yield return new ReasoningEndEvent
                            {
                                MessageId = currentReasoningId!
                            };
                            currentReasoningBaseId = null;
                            currentReasoningId = null;
                            currentReasoningMessageId = null;
                        }

                        yield return new ToolCallResultEvent
                        {
                            MessageId = chatResponse.MessageId,
                            ToolCallId = functionResultContent.CallId,
                            Content = SerializeResultContent(functionResultContent, jsonSerializerOptions) ?? "",
                            Role = AGUIRoles.Tool
                        };
                    }
                    else if (content is TextReasoningContent reasoningContent
                        && (!string.IsNullOrEmpty(reasoningContent.Text) || !string.IsNullOrEmpty(reasoningContent.ProtectedData)))
                    {
                        if (!string.Equals(currentReasoningBaseId, chatResponse.MessageId, StringComparison.Ordinal))
                        {
                            if (currentReasoningMessageId is not null)
                            {
                                yield return new ReasoningMessageEndEvent
                                {
                                    MessageId = currentReasoningMessageId
                                };
                                yield return new ReasoningEndEvent
                                {
                                    MessageId = currentReasoningId!
                                };
                            }

                            currentReasoningBaseId = chatResponse.MessageId;
                            currentReasoningId = Guid.NewGuid().ToString("N");
                            currentReasoningMessageId = Guid.NewGuid().ToString("N");

                            yield return new ReasoningStartEvent
                            {
                                MessageId = currentReasoningId
                            };
                            yield return new ReasoningMessageStartEvent
                            {
                                MessageId = currentReasoningMessageId
                            };
                        }

                        if (!string.IsNullOrEmpty(reasoningContent.Text))
                        {
                            yield return new ReasoningMessageContentEvent
                            {
                                MessageId = currentReasoningMessageId!,
                                Delta = reasoningContent.Text
                            };
                        }

                        if (!string.IsNullOrEmpty(reasoningContent.ProtectedData))
                        {
                            yield return new ReasoningEncryptedValueEvent
                            {
                                EntityId = currentReasoningMessageId!,
                                EncryptedValue = reasoningContent.ProtectedData
                            };
                        }
                    }
                    else if (content is DataContent dataContent)
                    {
                        if (MediaTypeHeaderValue.TryParse(dataContent.MediaType, out var mediaType) && mediaType.Equals(s_json))
                        {
                            // State snapshot event
                            yield return new StateSnapshotEvent
                            {
#if !NET
                                Snapshot = (JsonElement?)JsonSerializer.Deserialize(
                                dataContent.Data.ToArray(),
                                jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)))
#else
                                Snapshot = (JsonElement?)JsonSerializer.Deserialize(
                                dataContent.Data.Span,
                                jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)))
#endif
                            };
                        }
                        else if (mediaType is { } && mediaType.Equals(s_jsonPatchMediaType))
                        {
                            // State snapshot patch event must be a valid JSON patch,
                            // but its not up to us to validate that here.
                            yield return new StateDeltaEvent
                            {
#if !NET
                                Delta = (JsonElement?)JsonSerializer.Deserialize(
                                dataContent.Data.ToArray(),
                                jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)))
#else
                                Delta = (JsonElement?)JsonSerializer.Deserialize(
                                dataContent.Data.Span,
                                jsonSerializerOptions.GetTypeInfo(typeof(JsonElement)))
#endif
                            };
                        }
                        else
                        {
                            // Text content event
                            yield return new TextMessageContentEvent
                            {
                                MessageId = chatResponse.MessageId!,
#if !NET
                                Delta = Encoding.UTF8.GetString(dataContent.Data.ToArray())
#else
                                Delta = Encoding.UTF8.GetString(dataContent.Data.Span)
#endif
                            };
                        }
                    }
                }
            }
        }

        // End the last reasoning block if there was one
        if (currentReasoningMessageId is not null)
        {
            yield return new ReasoningMessageEndEvent
            {
                MessageId = currentReasoningMessageId
            };
            yield return new ReasoningEndEvent
            {
                MessageId = currentReasoningId!
            };
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

    private static string? SerializeResultContent(FunctionResultContent functionResultContent, JsonSerializerOptions options)
    {
        return functionResultContent.Result switch
        {
            null => null,
            string str => str,
            JsonElement jsonElement => jsonElement.GetRawText(),
            _ => JsonSerializer.Serialize(functionResultContent.Result, options.GetTypeInfo(functionResultContent.Result.GetType())),
        };
    }
}
