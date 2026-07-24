// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides the information available to a <see cref="RoutingChatClient"/> router and fallback factory
/// when deciding which inner client should handle a request.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class RoutingContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="RoutingContext"/> class.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent"/> executing the current run.</param>
    /// <param name="session">The <see cref="AgentSession"/> associated with the current run.</param>
    /// <param name="messages">The messages being sent in the current request.</param>
    /// <param name="options">The chat options for the current request, if any.</param>
    /// <param name="innerClients">The registered inner clients keyed by destination name.</param>
    /// <param name="activeDestination">The currently active destination key for the session.</param>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public RoutingContext(
        AIAgent agent,
        AgentSession session,
        IReadOnlyList<ChatMessage> messages,
        ChatOptions? options,
        IReadOnlyDictionary<string, IChatClient> innerClients,
        string? activeDestination)
    {
        this.Agent = agent;
        this.Session = session;
        this.Messages = messages;
        this.Options = options;
        this.InnerClients = innerClients;
        this.ActiveDestination = activeDestination;
    }

    /// <summary>
    /// Gets the <see cref="AIAgent"/> executing the current run.
    /// </summary>
    public AIAgent Agent { get; }

    /// <summary>
    /// Gets the <see cref="AgentSession"/> associated with the current run.
    /// </summary>
    public AgentSession Session { get; }

    /// <summary>
    /// Gets the messages being sent in the current request.
    /// </summary>
    public IReadOnlyList<ChatMessage> Messages { get; }

    /// <summary>
    /// Gets the chat options for the current request, if any.
    /// </summary>
    public ChatOptions? Options { get; }

    /// <summary>
    /// Gets the registered inner clients keyed by destination name.
    /// </summary>
    public IReadOnlyDictionary<string, IChatClient> InnerClients { get; }

    /// <summary>
    /// Gets the currently active destination key for the session, or <see langword="null"/> when the request
    /// is routed directly to the fallback factory.
    /// </summary>
    /// <remarks>
    /// This is the value returned by the default router. It reflects the destination stored in the
    /// session's <see cref="RoutingState"/> (or the value produced by the state initializer for a new session).
    /// </remarks>
    public string? ActiveDestination { get; }
}
