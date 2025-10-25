// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a user input response.
/// </summary>
public sealed class UserMessageResponse
{
    /// <summary>
    /// The response value.
    /// </summary>
    public ChatMessage Value { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="UserMessageResponse"/> class.
    /// </summary>
    /// <param name="value">The response value.</param>
    [JsonConstructor]
    public UserMessageResponse(ChatMessage value)
    {
        this.Value = value;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="UserMessageResponse"/> class.
    /// </summary>
    /// <param name="value">The response value.</param>
    public UserMessageResponse(string value)
    {
        this.Value = new ChatMessage(ChatRole.User, value);
    }
}
