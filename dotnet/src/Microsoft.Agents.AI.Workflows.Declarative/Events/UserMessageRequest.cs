// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for user input.
/// </summary>
public sealed class UserMessageRequest
{
    /// <summary>
    /// An optional prompt for the user.
    /// </summary>
    /// <remarks>
    /// This prompt is utilized for the "Question" action type in the Declarative Workflow,
    /// but is redundant when the user is responding to an agent since the agent's message
    /// is the implicit prompt.
    /// </remarks>
    public string? Prompt { get; }

    [JsonConstructor]
    internal UserMessageRequest(string? prompt = null)
    {
        this.Prompt = prompt;
    }
}
