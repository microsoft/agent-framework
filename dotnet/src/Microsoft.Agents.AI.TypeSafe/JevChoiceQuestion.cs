// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents a Choice question, which selects one of the named alternatives in <see cref="Criteria"/>.
/// </summary>
/// <remarks>
/// The answer is a <see cref="JevChoiceResponse"/>. This type mirrors <c>ChoiceQuestion</c> of the official TypeSafe SDK.
/// </remarks>
[Description("A Choice question: selects one of the named alternatives in criteria.")]
public sealed class JevChoiceQuestion : JevQuestion
{
    /// <summary>
    /// Gets or sets the alternatives, keyed by the label that the answer returns.
    /// </summary>
    /// <remarks>
    /// Each value describes the alternative as text or JSON, or is <see cref="JevEntry.Null"/> when the label is
    /// enough. Jev accepts from 1 to 255 alternatives.
    /// </remarks>
    [JsonPropertyName("criteria")]
    [Description("The alternatives, keyed by the label that the answer returns. Each value describes the alternative as text or JSON, or is null when the label is enough. From 1 to 255 alternatives.")]
    public required IReadOnlyDictionary<string, JevEntry> Criteria { get; set; }
}
