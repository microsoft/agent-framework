// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for AI agents that delegate operations to an inner agent
/// instance while allowing for extensibility and customization.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="DelegatingAIAgent"/> implements the decorator pattern for <see cref="AIAgent"/>s, enabling the creation of agent pipelines
/// where each layer can add functionality while delegating core operations to an underlying agent. This pattern is
/// fundamental to building composable agent architectures.
/// </para>
/// <para>
/// The default implementation provides transparent pass-through behavior, forwarding all operations to the inner agent.
/// Derived classes can override specific methods to add custom behavior while maintaining compatibility with the agent interface.
/// </para>
/// </remarks>
public class DelegatingAIAgent : AIAgent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DelegatingAIAgent"/> class with the specified inner agent.
    /// </summary>
    /// <param name="innerAgent">The underlying agent instance that will handle the core operations.</param>
    /// <exception cref="ArgumentNullException"><paramref name="innerAgent"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// The inner agent serves as the foundation of the delegation chain. All operations not overridden by
    /// derived classes will be forwarded to this agent.
    /// </remarks>
    protected DelegatingAIAgent(AIAgent innerAgent)
    {
        this.InnerAgent = Throw.IfNull(innerAgent);
    }

    /// <summary>
    /// Gets the inner agent instance that receives delegated operations.
    /// </summary>
    /// <value>
    /// The underlying <see cref="AIAgent"/> instance that handles core agent operations.
    /// </value>
    /// <remarks>
    /// Derived classes can use this property to access the inner agent for custom delegation scenarios
    /// or to forward operations with additional processing.
    /// </remarks>
    protected AIAgent InnerAgent { get; }

    /// <inheritdoc />
    protected override string? IdCore => this.InnerAgent.Id;

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
