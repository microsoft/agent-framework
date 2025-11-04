// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more user-input responses.
/// </summary>
public sealed class ExternalInputResponse
{
    /// <summary>
    /// The external input message.
    /// </summary>
    public ChatMessage Input { get; }

    [JsonConstructor]
    internal ExternalInputResponse(ChatMessage input)
    {
        this.Input = input;
    }
}
