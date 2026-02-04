// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Session for A2A based agents.
/// </summary>
public sealed class A2AAgentSession : AgentSession
{
    internal A2AAgentSession()
    {
    }

    internal A2AAgentSession(JsonElement serializedSessionState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedSessionState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedSessionState));
        }

        var state = serializedSessionState.Deserialize(
            A2AJsonUtilities.DefaultOptions.GetTypeInfo(typeof(A2AAgentSessionState))) as A2AAgentSessionState;

        if (state?.ContextId is string contextId)
        {
            this.ContextId = contextId;
        }

        if (state?.TaskId is string taskId)
        {
            this.TaskId = taskId;
        }
    }

    /// <summary>
    /// Gets the ID for the current conversation with the A2A agent.
    /// </summary>
    public string? ContextId { get; internal set; }

    /// <summary>
    /// Gets the ID for the task the agent is currently working on.
    /// </summary>
    public string? TaskId { get; internal set; }

    /// <inheritdoc/>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var state = new A2AAgentSessionState
        {
            ContextId = this.ContextId,
            TaskId = this.TaskId
        };

        return JsonSerializer.SerializeToElement(state, A2AJsonUtilities.DefaultOptions.GetTypeInfo(typeof(A2AAgentSessionState)));
    }

    internal sealed class A2AAgentSessionState
    {
        public string? ContextId { get; set; }

        public string? TaskId { get; set; }
    }
}
