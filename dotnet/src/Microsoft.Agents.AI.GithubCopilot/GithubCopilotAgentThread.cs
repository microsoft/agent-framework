// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GithubCopilot;

/// <summary>
/// Represents a thread for a GitHub Copilot agent conversation.
/// </summary>
public sealed class GithubCopilotAgentThread : AgentThread
{
    /// <summary>
    /// Gets or sets the session ID for the GitHub Copilot conversation.
    /// </summary>
    public string? SessionId { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentThread"/> class.
    /// </summary>
    public GithubCopilotAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentThread"/> class from serialized data.
    /// </summary>
    /// <param name="serializedThread">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serialization options.</param>
    internal GithubCopilotAgentThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        // Try both SessionId (PascalCase) and sessionId (camelCase) for compatibility
#pragma warning disable CA1507 // Use nameof to express symbol names - Need to check both casings for compatibility
        if (serializedThread.TryGetProperty("SessionId", out JsonElement sessionIdElement) ||
            serializedThread.TryGetProperty("sessionId", out sessionIdElement))
#pragma warning restore CA1507
        {
            this.SessionId = sessionIdElement.GetString();
        }
    }

    /// <inheritdoc/>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        GithubCopilotAgentThreadState state = new()
        {
            SessionId = this.SessionId
        };

        return JsonSerializer.SerializeToElement(
            state,
            GithubCopilotJsonUtilities.DefaultOptions.GetTypeInfo(typeof(GithubCopilotAgentThreadState)));
    }

    internal sealed class GithubCopilotAgentThreadState
    {
        public string? SessionId { get; set; }
    }
}
