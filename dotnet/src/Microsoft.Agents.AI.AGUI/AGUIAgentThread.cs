// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="AgentThread"/> implementation for AG-UI agents.
/// </summary>
internal sealed class AGUIAgentThread : InMemoryAgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgentThread"/> class.
    /// </summary>
    public AGUIAgentThread()
        : base()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">The serialized thread state.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    public AGUIAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(serializedThreadState, jsonSerializerOptions)
    {
    }
}
