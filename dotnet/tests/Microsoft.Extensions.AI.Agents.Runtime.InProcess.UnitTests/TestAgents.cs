// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public abstract class TestAgent : BaseAgent
{
    internal List<object> ReceivedMessages = [];

    protected TestAgent(AgentId id, IAgentRuntime runtime, string description)
        : base(id, runtime, description)
    {
    }
}

/// <summary>
/// A test agent that captures the messages it receives and
/// is able to save and load its state.
/// </summary>
public sealed class MockAgent : TestAgent, IHandle<string>
{
    public MockAgent(AgentId id, IAgentRuntime runtime, string description)
        : base(id, runtime, description) { }

    public ValueTask HandleAsync(string item, MessageContext messageContext)
    {
        this.ReceivedMessages.Add(item);
        return default;
    }

    public override async ValueTask<JsonElement> SaveStateAsync()
    {
        JsonElement json = JsonSerializer.SerializeToElement(this.ReceivedMessages);
        return json;
    }

    public override ValueTask LoadStateAsync(JsonElement state)
    {
        this.ReceivedMessages = JsonSerializer.Deserialize<List<object>>(state) ?? throw new InvalidOperationException("Failed to deserialize state");
        return default;
    }
}
