// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a user input response.
/// </summary>
public sealed class InputResponse
{
    /// <summary>
    /// The response value.
    /// </summary>
    public string Value { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="InputResponse"/> class.
    /// </summary>
    /// <param name="value">The response value.</param>
    [JsonConstructor]
    public InputResponse(string value)
    {
        this.Value = value;
    }
}
