// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.CopilotStudio;

/// <summary>
/// Thread for CopilotStudio based agents.
/// </summary>
public class CopilotStudioAgentThread : ServiceIdAgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="CopilotStudioAgentThread"/> class with the provided conversation ID.
    /// </summary>
    /// <param name="conversationId">The ID for the current conversation with the Copilot Studio agent.</param>
    public CopilotStudioAgentThread(string conversationId) : base(conversationId)
    {
    }

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
