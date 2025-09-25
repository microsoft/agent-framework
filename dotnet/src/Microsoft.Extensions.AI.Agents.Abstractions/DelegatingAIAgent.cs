// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides an optional base class for an <see cref="AIAgent"/> that passes through calls to another instance.
/// </summary>
/// <remarks>
/// This is recommended as a base type when building agents that can be chained around an underlying <see cref="AIAgent"/>.
/// The default implementation simply passes each call to the inner agent instance.
/// </remarks>
public class DelegatingAIAgent : AIAgent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAIAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The wrapped agent instance.</param>
    protected DelegatingAIAgent(AIAgent innerAgent)
    {
        this.InnerAgent = Throw.IfNull(innerAgent);
    }

    /// <summary>Gets the inner <see cref="AIAgent" />.</summary>
    protected AIAgent InnerAgent { get; }

    /// <inheritdoc />
    public override string Id => this.InnerAgent.Id;

    /// <inheritdoc />
    public override string? Name => this.InnerAgent.Name;

    /// <inheritdoc />
    public override string? Description => this.InnerAgent.Description;

    /// <inheritdoc />
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        _ = Throw.IfNull(serviceType);

        // If the key is non-null, we don't know what it means so pass through to the inner service.
        return
            serviceKey is null && serviceType.IsInstanceOfType(this) ? this :
            this.InnerAgent.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc />
    public override AgentThread GetNewThread() => this.InnerAgent.GetNewThread();

    /// <inheritdoc />
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        => this.InnerAgent.DeserializeThread(serializedThread, jsonSerializerOptions);

    /// <inheritdoc />
    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.InnerAgent.RunAsync(messages, thread, options, cancellationToken);

    /// <inheritdoc />
    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        => this.InnerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
}
