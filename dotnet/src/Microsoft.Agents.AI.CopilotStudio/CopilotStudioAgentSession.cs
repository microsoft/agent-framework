// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.CopilotStudio;

/// <summary>
/// Session for CopilotStudio based agents.
/// </summary>
public sealed class CopilotStudioAgentSession : ServiceIdAgentSession
{
    internal CopilotStudioAgentSession()
    {
    }

    internal CopilotStudioAgentSession(JsonElement serializedSessionState, JsonSerializerOptions? jsonSerializerOptions = null) : base(serializedSessionState, jsonSerializerOptions)
    {
    }

    /// <summary>
    /// Gets the ID for the current conversation with the Copilot Studio agent.
    /// </summary>
    public string? ConversationId
    {
        get { return this.ServiceSessionId; }
        internal set { this.ServiceSessionId = value; }
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    internal new JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
        => base.Serialize(jsonSerializerOptions);
}
