// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents the result of a get value operation containing the retrieved value.
/// </summary>
/// <param name="value">The value retrieved from the actor's state, or null if not found.</param>
public class GetValueResult(JsonElement? value) : ActorReadResult
{
    /// <summary>
    /// Gets the value retrieved from the actor's state.
    /// </summary>
    [JsonPropertyName("value")]
    public JsonElement? Value { get; } = value;

    /// <summary>
    /// Gets the type of the read result operation.
    /// </summary>
    public override ActorReadResultType Type => ActorReadResultType.GetValue;
}
