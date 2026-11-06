// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the result of a Jev call: one typed answer per question of the <see cref="JevRequest"/>, with the model
/// and token usage.
/// </summary>
/// <remarks>
/// This type mirrors <c>SystemOneResult</c> of the official TypeSafe SDK. Its JSON form is the result of the
/// <see cref="AIFunction"/> that <see cref="JevAIToolBuilder"/> creates.
/// </remarks>
public sealed class JevResult
{
    /// <summary>
    /// Gets or sets the model that answered the request.
    /// </summary>
    [JsonPropertyName("model")]
    [Description("The model that answered the request.")]
    public required string Model { get; set; }

    /// <summary>
    /// Gets or sets the answers, keyed by the ID of the question they answer.
    /// </summary>
    [JsonPropertyName("answers")]
    [Description("One answer per question, keyed by the question ID.")]
    public required IReadOnlyDictionary<string, JevResponse> Answers { get; set; }

    /// <summary>
    /// Gets or sets the token usage of the request.
    /// </summary>
    [JsonPropertyName("usage")]
    [Description("The token usage of the request.")]
    public required JevUsage Usage { get; set; }
}
