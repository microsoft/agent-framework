// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents Jev's answer to one question of a <see cref="JevRequest"/>.
/// </summary>
/// <remarks>
/// The JSON <c>type</c> property matches the kind of the question: <c>choice</c> (<see cref="JevChoiceResponse"/>),
/// <c>score</c> (<see cref="JevScoreResponse"/>), or <c>noul</c> (<see cref="JevNoulResponse"/>). The derived types
/// mirror <c>ChoiceResponse</c>, <c>ScoreResponse</c>, and <c>NoulResponse</c> of the official TypeSafe SDK.
/// </remarks>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(JevChoiceResponse), "choice")]
[JsonDerivedType(typeof(JevScoreResponse), "score")]
[JsonDerivedType(typeof(JevNoulResponse), "noul")]
public abstract class JevResponse
{
    // Only the three response kinds that the Jev API returns can exist.
    private protected JevResponse()
    {
    }
}
