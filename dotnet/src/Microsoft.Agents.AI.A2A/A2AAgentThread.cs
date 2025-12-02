// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Thread for A2A based agents.
/// </summary>
public sealed class A2AAgentThread : AgentThread
{
    internal A2AAgentThread()
    {
    }

    internal A2AAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = serializedThreadState.Deserialize(
            A2AJsonUtilities.DefaultOptions.GetTypeInfo(typeof(A2AAgentThreadState))) as A2AAgentThreadState;

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
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var state = new A2AAgentThreadState
        {
            ContextId = this.ContextId,
            TaskId = this.TaskId
        };

        return JsonSerializer.SerializeToElement(state, A2AJsonUtilities.DefaultOptions.GetTypeInfo(typeof(A2AAgentThreadState)));
    }

    internal sealed class A2AAgentThreadState
    {
        public string? ContextId { get; set; }

        public string? TaskId { get; set; }
    }
}
