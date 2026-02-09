// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

internal sealed class TestAIAgent : AIAgent
{
    public Func<string>? NameFunc;
    public Func<string>? DescriptionFunc;

    public readonly Func<JsonElement, JsonSerializerOptions?, AgentSession> DeserializeSessionFunc = delegate { throw new NotSupportedException(); };
    public readonly Func<AgentSession> CreateSessionFunc = delegate { throw new NotSupportedException(); };
    public Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken, Task<AgentResponse>> RunAsyncFunc = delegate { throw new NotSupportedException(); };
    public Func<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken, IAsyncEnumerable<AgentResponseUpdate>> RunStreamingAsyncFunc = delegate { throw new NotSupportedException(); };
    public Func<Type, object?, object?>? GetServiceFunc;

    public override string? Name => this.NameFunc?.Invoke() ?? base.Name;

    public override string? Description => this.DescriptionFunc?.Invoke() ?? base.Description;

    protected override JsonElement SerializeSessionCore(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
        => throw new NotImplementedException();

    protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default) =>
        new(this.DeserializeSessionFunc(serializedState, jsonSerializerOptions));

    protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
        new(this.CreateSessionFunc());

    protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        this.RunAsyncFunc(messages, session, options, cancellationToken);

    protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        this.RunStreamingAsyncFunc(messages, session, options, cancellationToken);

    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        this.GetServiceFunc is { } func ? func(serviceType, serviceKey) :
        base.GetService(serviceType, serviceKey);
}
