// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Threading.Tasks;
using GitHub.Copilot.SDK;

namespace Microsoft.Agents.AI.GithubCopilot;

/// <summary>
/// Represents a thread for a GitHub Copilot agent conversation.
/// </summary>
public sealed class GithubCopilotAgentThread : AgentThread, IAsyncDisposable
{
    /// <summary>
    /// Gets or sets the session ID for the GitHub Copilot conversation.
    /// </summary>
    public string? SessionId { get; internal set; }

    /// <summary>
    /// Gets or sets the active Copilot session.
    /// </summary>
    internal CopilotSession? Session { get; set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentThread"/> class.
    /// </summary>
    internal GithubCopilotAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="GithubCopilotAgentThread"/> class from serialized data.
    /// </summary>
    /// <param name="serializedThread">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serialization options.</param>
    internal GithubCopilotAgentThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
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

    /// <summary>
    /// Disposes the thread and releases the session.
    /// </summary>
    /// <returns>A value task representing the asynchronous dispose operation.</returns>
    public async ValueTask DisposeAsync()
    {
        if (this.Session is not null)
        {
            await this.Session.DisposeAsync().ConfigureAwait(false);
            this.Session = null;
        }
    }

    internal sealed class State
    {
        public string? SessionId { get; set; }
    }
}
