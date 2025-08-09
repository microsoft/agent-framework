// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using A2A;

namespace Microsoft.Extensions.AI.Agents.A2A.Internal;

/// <summary>
/// A2A agent that wraps an existing AIAgent and provides A2A-specific thread wrapping.
/// </summary>
internal sealed class A2AAgent : AIAgent
{
    private readonly AIAgent _innerAgent;
    private readonly TaskManager _taskManager;

    public A2AAgent(AIAgent innerAgent, TaskManager taskManager)
    {
        this._innerAgent = innerAgent ?? throw new ArgumentNullException(nameof(innerAgent));
        this._taskManager = taskManager ?? throw new ArgumentNullException(nameof(taskManager));
    }

    // Forward all properties to the inner agent
    public override string Id => this._innerAgent.Id;
    public override string? Name => this._innerAgent.Name;
    public override string? Description => this._innerAgent.Description;

    // Delegate the core methods to the inner agent
    public override Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        if (options is not A2AAgentRunOptions a2aRunOptions)
        {
            throw new ArgumentException($"Options must be of type {typeof(A2AAgentRunOptions)}.", nameof(options));
        }

        thread ??= this._innerAgent.GetNewThread();
        thread = new A2AAgentThreadWrapper(thread, this._taskManager, a2aRunOptions.TaskId);

        return this._innerAgent.RunAsync(messages, thread, options, cancellationToken);
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return this._innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
    }
}
