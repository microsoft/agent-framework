// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for external input.
/// </summary>
public sealed class ExternalInputRequest
{
    /// <summary>
    /// The source message that triggered the request for external input.
    /// </summary>
    public ChatMessage Message { get; }

    [JsonConstructor]
    internal ExternalInputRequest(ChatMessage message)
    {
        this.Message = message;
    }
}
