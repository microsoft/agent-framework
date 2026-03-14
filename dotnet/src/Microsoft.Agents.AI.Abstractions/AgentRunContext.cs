// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>Provides context for an in-flight agent run.</summary>
public sealed class AgentRunContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentRunContext"/> class.
    /// </summary>
    /// <param name="agent">The <see cref="AIAgent"/> that is executing the current run.</param>
    /// <param name="session">The <see cref="AgentSession"/> that is associated with the current run if any.</param>
    /// <param name="requestMessages">The request messages passed into the current run.</param>
    /// <param name="agentRunOptions">The <see cref="AgentRunOptions"/> that was passed to the current run.</param>
    public AgentRunContext(
        AIAgent agent,
        AgentSession? session,
        IReadOnlyCollection<ChatMessage> requestMessages,
        AgentRunOptions? agentRunOptions)
    {
        this.Agent = Throw.IfNull(agent);
        this.Session = session;
        this.RequestMessages = Throw.IfNull(requestMessages);
        this.RunOptions = agentRunOptions;
    }

    /// <summary>Gets the <see cref="AIAgent"/> that is executing the current run.</summary>
    public AIAgent Agent { get; }

    /// <summary>Gets the <see cref="AgentSession"/> that is associated with the current run.</summary>
    public AgentSession? Session { get; }

    /// <summary>Gets the request messages passed into the current run.</summary>
    public IReadOnlyCollection<ChatMessage> RequestMessages { get; }

    /// <summary>Gets the <see cref="AgentRunOptions"/> that was passed to the current run.</summary>
    public AgentRunOptions? RunOptions { get; }
}
