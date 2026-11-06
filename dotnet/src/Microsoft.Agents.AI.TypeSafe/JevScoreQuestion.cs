// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents a Score question, which assigns a score using the ordered rubric in <see cref="Criteria"/>.
/// </summary>
/// <remarks>
/// The answer is a <see cref="JevScoreResponse"/>, whose score is weighted by probability and can fall between
/// levels. This type mirrors <c>ScoreQuestion</c> of the official TypeSafe SDK.
/// </remarks>
[Description("A Score question: assigns a score using the ordered rubric in criteria.")]
public sealed class JevScoreQuestion : JevQuestion
{
    /// <summary>
    /// Gets or sets the rubric: one description per score, indexed from zero (the lowest score).
    /// </summary>
    /// <remarks>
    /// Each description is text or JSON. The official SDK types also allow <see cref="JevEntry.Null"/> to leave a
    /// score undescribed, but the API rejects it. A Score needs from 2 to 10 scores.
    /// </remarks>
    [JsonPropertyName("criteria")]
    [Description("The rubric: one description per score, as text or JSON, indexed from zero (the lowest score). From 2 to 10 scores.")]
    public required IReadOnlyList<JevEntry> Criteria { get; set; }
}
