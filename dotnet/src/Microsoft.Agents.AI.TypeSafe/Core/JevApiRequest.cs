// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The body of <c>POST /v1/systemone</c>: a <see cref="JevRequest"/> with the model resolved, like
/// <c>SystemOneRequestPayload</c> of the official TypeSafe SDK.
/// </summary>
internal sealed class JevApiRequest
{
    [JsonPropertyName("state")]
    public required JevEntry State { get; init; }

    [JsonPropertyName("model")]
    public required string Model { get; init; }

    [JsonPropertyName("questions")]
    public required IReadOnlyDictionary<string, JevQuestion> Questions { get; init; }
}
