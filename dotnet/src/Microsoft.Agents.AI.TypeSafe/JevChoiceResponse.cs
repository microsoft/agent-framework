// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the answer to a <see cref="JevChoiceQuestion"/>: the selected label and its probabilities.
/// </summary>
/// <remarks>
/// This type mirrors <c>ChoiceResponse</c> of the official TypeSafe SDK.
/// </remarks>
[Description("The answer to a Choice question: the selected label and its probabilities.")]
public sealed class JevChoiceResponse : JevResponse
{
    /// <summary>
    /// Gets or sets the selected label.
    /// </summary>
    [JsonPropertyName("choice")]
    [Description("The selected label.")]
    public required string Choice { get; set; }

    /// <summary>
    /// Gets or sets the reported confidence in the selected label, from 0 to 1.
    /// </summary>
    [JsonPropertyName("confidence")]
    [Description("Reported confidence in the selected label, from 0 to 1. Treat low confidence as uncertain.")]
    public required double Confidence { get; set; }

    /// <summary>
    /// Gets or sets the probabilities, keyed by label. They sum to 1.
    /// </summary>
    [JsonPropertyName("probabilities")]
    [Description("Probabilities keyed by label. They sum to 1.")]
    public required IReadOnlyDictionary<string, double> Probabilities { get; set; }
}
