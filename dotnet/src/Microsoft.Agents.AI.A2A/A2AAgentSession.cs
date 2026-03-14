// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.A2A;

/// <summary>
/// Session for A2A based agents.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class A2AAgentSession : AgentSession
{
    internal A2AAgentSession()
    {
    }

    [JsonConstructor]
    internal A2AAgentSession(string? contextId, string? taskId, AgentSessionStateBag? stateBag) : base(stateBag ?? new())
    {
        this.ContextId = contextId;
        this.TaskId = taskId;
    }

    /// <summary>
    /// Gets the ID for the current conversation with the A2A agent.
    /// </summary>
    [JsonPropertyName("contextId")]
    public string? ContextId { get; internal set; }

    /// <summary>
    /// Gets the ID for the task the agent is currently working on.
    /// </summary>
    [JsonPropertyName("taskId")]
    public string? TaskId { get; internal set; }

    /// <inheritdoc/>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? A2AJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(A2AAgentSession)));
    }

    internal static A2AAgentSession Deserialize(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var jso = jsonSerializerOptions ?? A2AJsonUtilities.DefaultOptions;
        return serializedState.Deserialize(jso.GetTypeInfo(typeof(A2AAgentSession))) as A2AAgentSession
            ?? new A2AAgentSession();
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"ContextId = {this.ContextId}, TaskId = {this.TaskId}, StateBag Count = {this.StateBag.Count}";
}
