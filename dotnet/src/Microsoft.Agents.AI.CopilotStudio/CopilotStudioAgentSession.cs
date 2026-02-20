// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.CopilotStudio;

/// <summary>
/// Session for CopilotStudio based agents.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class CopilotStudioAgentSession : AgentSession
{
    internal CopilotStudioAgentSession()
    {
    }

    [JsonConstructor]
    internal CopilotStudioAgentSession(string? conversationId, AgentSessionStateBag? stateBag) : base(stateBag ?? new())
    {
        this.ConversationId = conversationId;
    }

    /// <summary>
    /// Gets the ID for the current conversation with the Copilot Studio agent.
    /// </summary>
    [JsonPropertyName("serviceSessionId")]
    public string? ConversationId { get; internal set; }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? CopilotStudioJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(CopilotStudioAgentSession)));
    }

    internal static CopilotStudioAgentSession Deserialize(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var jso = jsonSerializerOptions ?? CopilotStudioJsonUtilities.DefaultOptions;
        return serializedState.Deserialize(jso.GetTypeInfo(typeof(CopilotStudioAgentSession))) as CopilotStudioAgentSession
            ?? new CopilotStudioAgentSession();
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"ConversationId = {this.ConversationId}, StateBag Count = {this.StateBag.Count}";
}
