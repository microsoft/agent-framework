// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>A scriptable chat client: queued responses, recorded requests.</summary>
internal sealed class MockChatClient : IChatClient
{
    private readonly object _lock = new();

    public Queue<Func<List<ChatMessage>, ChatResponse>> Responses { get; } = new();

    public List<List<ChatMessage>> Requests { get; } = [];

    public int CallCount
    {
        get { lock (this._lock) { return this.Requests.Count; } }
    }

    public MockChatClient EnqueueText(string text)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => new ChatResponse(new ChatMessage(ChatRole.Assistant, text)));
        }

        return this;
    }

    public MockChatClient EnqueueResponse(ChatResponse response)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => response);
        }

        return this;
    }

    public MockChatClient EnqueueThrow(Exception exception)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => throw exception);
        }

        return this;
    }

    public MockChatClient EnqueueFunctionCall(string callId, string name, Dictionary<string, object?> arguments)
    {
        lock (this._lock)
        {
            this.Responses.Enqueue(_ => new ChatResponse(
                new ChatMessage(ChatRole.Assistant, [new FunctionCallContent(callId, name, arguments)])));
        }

        return this;
    }

    private ChatResponse NextResponse(IEnumerable<ChatMessage> messages)
    {
        lock (this._lock)
        {
            List<ChatMessage> request = [.. messages];
            this.Requests.Add(request);
            return this.Responses.Dequeue()(request);
        }
    }

    public Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        Task.FromResult(this.NextResponse(messages));

    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = this.NextResponse(messages);
        await Task.Yield();
        foreach (var update in response.ToChatResponseUpdates())
        {
            yield return update;
        }
    }

    public object? GetService(Type serviceType, object? serviceKey = null) =>
        serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    public void Dispose()
    {
    }
}
