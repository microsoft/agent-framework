// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Thread for A2A based agents.
/// </summary>
public sealed class A2AAgentThread : ServiceIdAgentThread
{
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
