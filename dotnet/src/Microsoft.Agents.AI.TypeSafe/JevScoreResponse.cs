// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the answer to a <see cref="JevScoreQuestion"/>: an expected score with its rubric and probabilities.
/// </summary>
/// <remarks>
/// This type mirrors <c>ScoreResponse</c> of the official TypeSafe SDK.
/// </remarks>
[Description("The answer to a Score question: an expected score with its rubric and probabilities.")]
public sealed class JevScoreResponse : JevResponse
{
    /// <summary>
    /// Gets or sets the expected score, which may fall between integer rubric levels.
    /// </summary>
    [JsonPropertyName("score")]
    [Description("Expected score, which may fall between integer rubric levels.")]
    public required double Score { get; set; }

    /// <summary>
    /// Gets or sets the reported confidence in the score, from 0 to 1.
    /// </summary>
    [JsonPropertyName("confidence")]
    [Description("Reported confidence in the score, from 0 to 1. Treat low confidence as uncertain.")]
    public required double Confidence { get; set; }

    /// <summary>
    /// Gets or sets the rubric descriptions, keyed by score. They echo the rubric of the question.
    /// </summary>
    [JsonPropertyName("legend")]
    [Description("Rubric descriptions keyed by score.")]
    public required IReadOnlyDictionary<string, JevEntry> Legend { get; set; }

    /// <summary>
    /// Gets or sets the probabilities, keyed by score. They sum to 1.
    /// </summary>
    [JsonPropertyName("probabilities")]
    [Description("Probabilities keyed by score. They sum to 1.")]
    public required IReadOnlyDictionary<string, double> Probabilities { get; set; }
}
