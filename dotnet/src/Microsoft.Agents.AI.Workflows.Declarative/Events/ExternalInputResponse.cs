// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents the response to a <see cref="ExternalInputRequest"/>.
/// </summary>
public sealed class ExternalInputResponse
{
    /// <summary>
    /// The message being provided as external input to the workflow.
    /// </summary>
    public ChatMessage Message { get; }

    /// <summary>
    /// Initializes a new instance of <see cref="ExternalInputResponse"/>.
    /// </summary>
    /// <param name="message">The external input message being provided to the workflow.</param>
    [JsonConstructor]
    public ExternalInputResponse(ChatMessage message)
    {
        this.Message = message;
    }
}
