﻿// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Moq;

namespace Microsoft.Agents.Orchestration.UnitTest;

/// <summary>
/// Mock definition of <see cref="Agent"/>.
/// </summary>
internal sealed class MockAgent(int index) : Agent
{
    public static MockAgent CreateWithResponse(int index, string response)
    {
        return new(index)
        {
            Response = [new(ChatRole.Assistant, response)]
        };
    }

    public int InvokeCount { get; private set; }

    public IReadOnlyList<ChatMessage> Response { get; set; } = [];

    public override string? Name => $"testagent{index}";

    public override string? Description => $"test {index}";

    public override AgentThread GetNewThread()
    {
        return new AgentThread() { Id = Guid.NewGuid().ToString() };
    }

    public override async Task<ChatResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        this.InvokeCount++;
        if (thread == null)
        {
            Mock<AgentThread> mockThread = new(MockBehavior.Strict);
            thread = mockThread.Object;
        }

        await (options?.OnIntermediateMessages?.Invoke(this.Response) ?? Task.CompletedTask);

        return new ChatResponse(messages: [.. this.Response]);
    }

    public override async IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.InvokeCount++;

        await (options?.OnIntermediateMessages?.Invoke(this.Response) ?? Task.CompletedTask);

        foreach (ChatMessage message in this.Response)
        {
            yield return new ChatResponseUpdate(message.Role, message.Text);
        }
    }
}
