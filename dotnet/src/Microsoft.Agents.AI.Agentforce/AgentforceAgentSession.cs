// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Agentforce;

/// <summary>
/// Session for Salesforce Agentforce agents.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class AgentforceAgentSession : AgentSession
{
    internal AgentforceAgentSession()
    {
    }

    [JsonConstructor]
    internal AgentforceAgentSession(string? serviceSessionId, AgentSessionStateBag? stateBag)
        : base(stateBag ?? new())
    {
        this.ServiceSessionId = serviceSessionId;
    }

    /// <summary>
    /// Gets the Salesforce-assigned session ID for the current conversation with the Agentforce agent.
    /// </summary>
    [JsonPropertyName("serviceSessionId")]
    public string? ServiceSessionId { get; internal set; }

    /// <summary>
    /// Serializes the current session state to a <see cref="JsonElement"/>.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the session state.</returns>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? AgentforceJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(AgentforceAgentSession)));
    }

    /// <summary>
    /// Deserializes an <see cref="AgentforceAgentSession"/> from its JSON representation.
    /// </summary>
    /// <param name="serializedState">The serialized JSON state.</param>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A deserialized <see cref="AgentforceAgentSession"/> instance.</returns>
    internal static AgentforceAgentSession Deserialize(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var jso = jsonSerializerOptions ?? AgentforceJsonUtilities.DefaultOptions;
        return serializedState.Deserialize(jso.GetTypeInfo(typeof(AgentforceAgentSession))) as AgentforceAgentSession
            ?? new AgentforceAgentSession();
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"ServiceSessionId = {this.ServiceSessionId}, StateBag Count = {this.StateBag.Count}";
}
