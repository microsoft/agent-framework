// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the answer to a <see cref="JevNoulQuestion"/>: the probability of yes.
/// </summary>
/// <remarks>
/// This type mirrors <c>NoulResponse</c> of the official TypeSafe SDK.
/// </remarks>
[Description("The answer to a Noul question: the probability of yes.")]
public sealed class JevNoulResponse : JevResponse
{
    /// <summary>
    /// Gets or sets the probability of a yes answer, from 0 to 1.
    /// </summary>
    [JsonPropertyName("noul")]
    [Description("Probability of a yes answer, from 0 to 1.")]
    public required double Noul { get; set; }
}
