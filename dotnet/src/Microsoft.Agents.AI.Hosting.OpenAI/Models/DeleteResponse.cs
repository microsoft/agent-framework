// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Models;

/// <summary>
/// Response for a delete operation.
/// </summary>
internal sealed class DeleteResponse
{
    /// <summary>
    /// The ID of the deleted object.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    /// <summary>
    /// The object type.
    /// </summary>
    [JsonPropertyName("object")]
    [SuppressMessage("Naming", "CA1720:Identifiers should not match keywords", Justification = "Matches OpenAI API specification")]
    public required string Object { get; init; }

    /// <summary>
    /// Whether the object was successfully deleted.
    /// </summary>
    [JsonPropertyName("deleted")]
    public required bool Deleted { get; init; }
}
