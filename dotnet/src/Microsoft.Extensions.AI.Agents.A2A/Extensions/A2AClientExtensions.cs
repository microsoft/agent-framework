// Copyright (c) Microsoft. All rights reserved.

using A2A;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Provides extension methods for <see cref="A2AClient"/>
/// to simplify the creation of A2A agents.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between A2A SDK client objects
/// and the Microsoft Extensions AI Agent framework.
/// <para>
/// They allow developers to easily create AI agents that can interact
/// with A2A agents by handling the conversion from A2A clients to
/// <see cref="A2AAgent"/> instances that implement the <see cref="AIAgent"/> interface.
/// </para>
/// </remarks>
public static class A2AClientExtensions
{
    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to create AI agents for A2A agents whose hosts support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#3-direct-configuration--private-discovery">Direct Configuration / Private Discovery</see>
    /// discovery mechanism.
    /// </remarks>
    /// <param name="client">The <see cref="A2AClient" /> to use for the agent.</param>
    /// <param name="id">The unique identifier for the agent.</param>
    /// <param name="name">The the name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="displayName">The display name of the agent.</param>
    /// <param name="loggerFactory">Optional logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static AIAgent GetAIAgent(this A2AClient client, string? id = null, string? name = null, string? description = null, string? displayName = null, ILoggerFactory? loggerFactory = null) =>
        new A2AAgent(client, id, name, description, displayName, loggerFactory);
}
