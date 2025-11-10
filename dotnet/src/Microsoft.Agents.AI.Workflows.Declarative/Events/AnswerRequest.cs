// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for user input in response to a `Question` action.
/// </summary>
public sealed class AnswerRequest
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
    internal AnswerRequest(string? prompt = null)
    {
        this.Prompt = prompt;
    }
}
