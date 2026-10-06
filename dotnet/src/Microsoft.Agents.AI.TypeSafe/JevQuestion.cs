// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents one typed question that Jev answers about the state of a <see cref="JevRequest"/>.
/// </summary>
/// <remarks>
/// The JSON <c>type</c> property selects the question kind: <c>choice</c> (<see cref="JevChoiceQuestion"/>),
/// <c>score</c> (<see cref="JevScoreQuestion"/>), or <c>noul</c> (<see cref="JevNoulQuestion"/>). It mirrors
/// <c>Question</c> of the official TypeSafe SDK.
/// </remarks>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(JevChoiceQuestion), "choice")]
[JsonDerivedType(typeof(JevScoreQuestion), "score")]
[JsonDerivedType(typeof(JevNoulQuestion), "noul")]
public abstract class JevQuestion
{
    // Only the three question kinds that the Jev API accepts can exist.
    private protected JevQuestion()
    {
    }

    /// <summary>
    /// Gets or sets what Jev should decide, rate, or check, as text or JSON, or <see langword="null"/> when the
    /// criteria say enough.
    /// </summary>
    /// <remarks>
    /// Structured instructions hold the question in one field and data it refers to in others, for example
    /// <c>{ "potential_duplicate": { ... }, "question": "Is the resume for the same person as `potential_duplicate`?" }</c>.
    /// </remarks>
    [JsonPropertyName("instructions")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Description("What Jev should decide, rate, or check: text, or a JSON object that holds the question in one field and the data it refers to in others. Optional when the criteria say enough. Describe the idea rather than exact words, because Jev matches on meaning.")]
    public JevEntry? Instructions { get; set; }
}
