// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Provides contextual information for an orchestration operation, including topic, cancellation, logging, and response callback.
/// </summary>
public sealed class OrchestrationContext
{
    internal OrchestrationContext(
        string orchestration,
        TopicId topic,
        Func<IEnumerable<ChatMessage>, ValueTask>? responseCallback,
        Func<AgentRunResponseUpdate, ValueTask>? streamingCallback,
        ILoggerFactory loggerFactory,
        CancellationToken cancellationToken)
    {
        this.Orchestration = orchestration;
        this.Topic = topic;
        this.ResponseCallback = responseCallback;
        this.StreamingResponseCallback = streamingCallback;
        this.LoggerFactory = loggerFactory;
        this.CancellationToken = cancellationToken;
    }

    /// <summary>
    /// Gets the name or identifier of the orchestration.
    /// </summary>
    public string Orchestration { get; }

    /// <summary>
    /// Gets the identifier associated with orchestration topic.
    /// </summary>
    /// <remarks>
    /// All orchestration actors are subscribed to this topic.
    /// </remarks>
    public TopicId Topic { get; }

    /// <summary>
    /// Gets the cancellation token that can be used to observe cancellation requests for the orchestration.
    /// </summary>
    public CancellationToken CancellationToken { get; }

    /// <summary>
    /// Gets the associated logger factory for creating loggers within the orchestration context.
    /// </summary>
    public ILoggerFactory LoggerFactory { get; }

    /// <summary>
    /// Optional callback that is invoked for every agent response.
    /// </summary>
    public Func<IEnumerable<ChatMessage>, ValueTask>? ResponseCallback { get; }

    /// <summary>
    /// Optional callback that is invoked for every agent response.
    /// </summary>
    public Func<AgentRunResponseUpdate, ValueTask>? StreamingResponseCallback { get; }
}
