// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.CopilotStudio;

/// <summary>
/// Thread for CopilotStudio based agents.
/// </summary>
public sealed class CopilotStudioAgentThread : ServiceIdAgentThread
{
    internal CopilotStudioAgentThread()
    {
    }

    internal CopilotStudioAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null) : base(serializedThreadState, jsonSerializerOptions)
    {
    }

    /// <summary>
    /// Gets the ID for the current conversation with the Copilot Studio agent.
    /// </summary>
    public string? ConversationId
    {
        get { return this.ServiceThreadId; }
        internal set { this.ServiceThreadId = value; }
    }
}
