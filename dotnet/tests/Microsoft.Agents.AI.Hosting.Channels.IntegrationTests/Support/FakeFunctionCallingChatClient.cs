// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>
/// Two-turn fake <see cref="IChatClient"/> that drives a function-call loop deterministically:
/// turn 1 (no function results yet) emits a <see cref="FunctionCallContent"/> for the first advertised
/// tool; turn 2 (function results present) emits the final text answer. Combined with a
/// <see cref="ChatClientAgent"/> built with tools (which inserts <see cref="FunctionInvokingChatClient"/>),
/// this exercises end-to-end tool execution with no live model.
/// </summary>
internal sealed class FakeFunctionCallingChatClient : IChatClient
{
    public const string FinalAnswer = "The weather in Seattle is sunny.";

    private readonly IReadOnlyDictionary<string, object?> _arguments;

    /// <summary>Initializes the fake. <paramref name="arguments"/> are sent on the emitted function call.</summary>
    public FakeFunctionCallingChatClient(IReadOnlyDictionary<string, object?>? arguments = null)
    {
        this._arguments = arguments ?? new Dictionary<string, object?>();
    }

    public ChatClientMetadata Metadata => new("fake-function-calling");

    public async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
        => await this.GetStreamingResponseAsync(messages, options, cancellationToken).ToChatResponseAsync(cancellationToken).ConfigureAwait(false);

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var messageList = messages.ToList();
        var hasFunctionResults = messageList.Any(m => m.Contents.Any(c => c is FunctionResultContent));
        var messageId = Guid.NewGuid().ToString("N");

        if (hasFunctionResults)
        {
            yield return new ChatResponseUpdate(ChatRole.Assistant, FinalAnswer) { MessageId = messageId };
            yield break;
        }

        var tool = (options?.Tools ?? []).OfType<AIFunction>().FirstOrDefault();
        if (tool is null)
        {
            yield return new ChatResponseUpdate(ChatRole.Assistant, "No tools available.") { MessageId = messageId };
            yield break;
        }

        var callId = Guid.NewGuid().ToString("N");
        yield return new ChatResponseUpdate
        {
            MessageId = messageId,
            Role = ChatRole.Assistant,
            Contents = [new FunctionCallContent(callId, tool.Name, new Dictionary<string, object?>(this._arguments))],
        };

        await Task.Yield();
    }

    public object? GetService(Type serviceType, object? serviceKey = null) => null;

    public void Dispose()
    {
    }
}
