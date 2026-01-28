// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.GithubCopilot;

/// <summary>
/// Represents a session for a GitHub Copilot agent conversation.
/// </summary>
public sealed class GithubCopilotAgentSession : AgentSession
{
    /// <summary>
    /// Gets or sets the session ID for the GitHub Copilot conversation.
    /// </summary>
    public string? SessionId { get; internal set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentSession"/> class.
    /// </summary>
    internal GithubCopilotAgentSession()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentSession"/> class from serialized data.
    /// </summary>
    /// <param name="serializedThread">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serialization options.</param>
    internal GithubCopilotAgentSession(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        // The JSON serialization uses camelCase
        if (serializedThread.TryGetProperty("sessionId", out JsonElement sessionIdElement))
        {
            this.SessionId = sessionIdElement.GetString();
        }
    }

    /// <inheritdoc/>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        State state = new()
        {
            SessionId = this.SessionId
        };

        return JsonSerializer.SerializeToElement(
            state,
            GithubCopilotJsonUtilities.DefaultOptions.GetTypeInfo(typeof(State)));
    }

    internal sealed class State
    {
        public string? SessionId { get; set; }
    }
}
