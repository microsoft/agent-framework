// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;

/// <summary>
/// Wraps a per-request <see cref="AIAgent"/> so that its <see cref="AIAgent.Id"/> reports a
/// caller-supplied stable value instead of the per-instance identifier the base type generates.
/// </summary>
/// <remarks>
/// <see cref="AgentSessionStore"/> implementations key persisted sessions by the pair
/// <c>(agent.Id, conversationId)</c>, and <see cref="AIAgent.Id"/> defaults to a value that is unique
/// per agent instance. The per-request factory overload of <c>MapAGUIServer</c> builds a fresh agent on
/// every request, so without a stable identity each request would compute a different session key and
/// the previously persisted session would never be found — silently resetting AG-UI thread
/// continuation every turn. Wrapping the per-request agent so its id is the logical agent name keeps
/// the session key constant across requests, matching the startup-capture overloads where a single
/// agent instance is reused.
/// </remarks>
internal sealed class StableIdentityAIAgent : DelegatingAIAgent
{
    private readonly string stableId;

    /// <summary>
    /// Initializes a new instance of the <see cref="StableIdentityAIAgent"/> class.
    /// </summary>
    /// <param name="innerAgent">The per-request agent to delegate all behavior to.</param>
    /// <param name="stableId">The stable identifier to report from <see cref="AIAgent.Id"/>.</param>
    public StableIdentityAIAgent(AIAgent innerAgent, string stableId)
        : base(innerAgent)
    {
        this.stableId = stableId;
    }

    /// <inheritdoc/>
    protected override string? IdCore => this.stableId;
}
