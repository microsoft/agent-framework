// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Specifies how the A2A hosting layer determines whether to return an
/// <c>AgentMessage</c> or an <c>AgentTask</c> from
/// <see cref="AIAgentExtensions"/>.
/// </summary>
public enum A2AResponseMode
{
    /// <summary>
    /// The decision is delegated to the agent. Background responses are enabled
    /// and if the agent returns a continuation token (indicating a long-running operation),
    /// an <c>AgentTask</c> is returned. Otherwise an <c>AgentMessage</c> is returned.
    /// </summary>
    Auto = 0,

    /// <summary>
    /// Always return an <c>AgentMessage</c>. Background responses are not enabled.
    /// This is suitable for lightweight, single-shot request-response interactions.
    /// </summary>
    Message = 1,

    /// <summary>
    /// Always return an <c>AgentTask</c>. A task is created and tracked for every
    /// request, even if the agent completes immediately. Background responses are enabled
    /// so the agent can signal long-running operations if supported.
    /// </summary>
    Task = 2,
}
