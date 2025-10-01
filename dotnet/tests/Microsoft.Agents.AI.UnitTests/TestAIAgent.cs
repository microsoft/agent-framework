﻿// Copyright (c) Microsoft. All rights reserved.

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

    public Func<JsonElement, JsonSerializerOptions?, AgentThread> DeserializeThreadFunc = delegate { throw new NotSupportedException(); };
    public Func<AgentThread> GetNewThreadFunc = delegate { throw new NotSupportedException(); };
    public Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, Task<AgentRunResponse>> RunAsyncFunc = delegate { throw new NotSupportedException(); };
    public Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken, IAsyncEnumerable<AgentRunResponseUpdate>> RunStreamingAsyncFunc = delegate { throw new NotSupportedException(); };
    public Func<Type, object?, object?>? GetServiceFunc;

    public override string? Name => this.NameFunc?.Invoke() ?? base.Name;

    public override string? Description => this.DescriptionFunc?.Invoke() ?? base.Description;

    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null) =>
        this.DeserializeThreadFunc(serializedThread, jsonSerializerOptions);

    public override AgentThread GetNewThread() =>
        this.GetNewThreadFunc();

    public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        this.RunAsyncFunc(messages, thread, options, cancellationToken);

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default) =>
        this.RunStreamingAsyncFunc(messages, thread, options, cancellationToken);

    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        this.GetServiceFunc is { } func ? func(serviceType, serviceKey) :
        base.GetService(serviceType, serviceKey);
}
