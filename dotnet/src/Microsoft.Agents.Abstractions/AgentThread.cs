// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
public class AgentThread
{
    /// <summary>
    /// Gets or sets the id of the current thread.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This id may be null if the thread has no id, or
    /// if it represents a service-owned thread but the service
    /// has not yet been called to create the thread.
    /// </para>
    /// <para>
    /// The id may also change over time where the <see cref="AgentThread"/>
    /// is a proxy to a service owned thread that forks on each agent invocation.
    /// </para>
    /// </remarks>
    public string? Id { get; set; }
}
