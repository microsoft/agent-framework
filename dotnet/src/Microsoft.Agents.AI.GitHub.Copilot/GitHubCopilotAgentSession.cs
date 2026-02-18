// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.GitHub.Copilot;

/// <summary>
/// Represents a session for a GitHub Copilot agent conversation.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class GitHubCopilotAgentSession : AgentSession
{
    /// <summary>
    /// Gets or sets the session ID for the GitHub Copilot conversation.
    /// </summary>
    [JsonPropertyName("sessionId")]
    public string? SessionId { get; internal set; }

    /// <summary>
    /// Initializes a new instance of the <see cref="GitHubCopilotAgentSession"/> class.
    /// </summary>
    internal GitHubCopilotAgentSession()
    {
    }

    [JsonConstructor]
    internal GitHubCopilotAgentSession(string? sessionId, AgentSessionStateBag? stateBag) : base(stateBag ?? new())
    {
        this.SessionId = sessionId;
    }

    /// <inheritdoc/>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? GitHubCopilotJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(GitHubCopilotAgentSession)));
    }

    internal static GitHubCopilotAgentSession Deserialize(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var jso = jsonSerializerOptions ?? GitHubCopilotJsonUtilities.DefaultOptions;
        return serializedState.Deserialize(jso.GetTypeInfo(typeof(GitHubCopilotAgentSession))) as GitHubCopilotAgentSession
            ?? new GitHubCopilotAgentSession();
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"SessionId = {this.SessionId}, StateBag Count = {this.StateBag.Count}";
}
