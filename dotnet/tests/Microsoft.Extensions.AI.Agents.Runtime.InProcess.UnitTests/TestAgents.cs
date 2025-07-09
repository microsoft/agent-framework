﻿// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess.Tests;

public abstract class TestAgent : RuntimeActor
{
    internal List<object> ReceivedMessages = [];

    protected TestAgent(ActorId id, IAgentRuntime runtime, string description)
        : base(id, runtime, description)
    {
    }
}

/// <summary>
/// A test agent that captures the messages it receives and
/// is able to save and load its state.
/// </summary>
public sealed class MockAgent : TestAgent
{
    public MockAgent(ActorId id, IAgentRuntime runtime, string description) : base(id, runtime, description)
    {
        this.RegisterMessageHandler<string>(this.HandleAsync);
    }

    public ValueTask HandleAsync(string item, MessageContext messageContext, CancellationToken cancellationToken)
    {
        this.ReceivedMessages.Add(item);
        return default;
    }

    public override async ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default)
    {
        JsonElement json = JsonSerializer.SerializeToElement(this.ReceivedMessages);
        return json;
    }

    public override ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default)
    {
        this.ReceivedMessages = JsonSerializer.Deserialize<List<object>>(state) ?? throw new InvalidOperationException("Failed to deserialize state");
        return default;
    }
}
