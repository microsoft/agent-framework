﻿// Copyright (c) Microsoft. All rights reserved.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
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

    public override AgentThread DeserializeThread(string threadStateJson, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new AgentThread(threadStateJson, jsonSerializerOptions);
    }

    public override Task<AgentRunResponse> RunAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        this.InvokeCount++;
        if (thread == null)
        {
            Mock<AgentThread> mockThread = new(MockBehavior.Strict);
            thread = mockThread.Object;
        }

        return Task.FromResult(new AgentRunResponse(messages: [.. this.Response]));
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        this.InvokeCount++;

        return this.Response.Select(message => new AgentRunResponseUpdate(message.Role, message.Text)).ToAsyncEnumerable();
    }
}
