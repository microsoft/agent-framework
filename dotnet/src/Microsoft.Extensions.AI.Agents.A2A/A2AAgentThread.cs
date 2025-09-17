// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.A2A;

/// <summary>
/// Thread for A2A based agents.
/// </summary>
public class A2AAgentThread : ServiceIdAgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="A2AAgentThread"/> class with the provided A2A context ID.
    /// </summary>
    /// <param name="contextId">The ID for the current conversation with the A2A agent.</param>
    public A2AAgentThread(string contextId) : base(contextId)
    {
    }

    internal A2AAgentThread()
    {
    }

    internal A2AAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null) : base(serializedThreadState, jsonSerializerOptions)
    {
    }

    /// <summary>
    /// Gets the ID for the current conversation with the A2A agent.
    /// </summary>
    public string? ContextId
    {
        get { return this.ServiceThreadId; }
        internal set { this.ServiceThreadId = value; }
    }
}
