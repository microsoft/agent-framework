// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Describes the yes and no outcomes of a <see cref="JevNoulQuestion"/>.
/// </summary>
public sealed class JevNoulCriteria
{
    /// <summary>
    /// Gets or sets the description of the yes outcome, as text or JSON.
    /// </summary>
    [JsonPropertyName("true")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Description("Description of the yes outcome, as text or JSON.")]
    public JevEntry? True { get; set; }

    /// <summary>
    /// Gets or sets the description of the no outcome, as text or JSON.
    /// </summary>
    [JsonPropertyName("false")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Description("Description of the no outcome, as text or JSON.")]
    public JevEntry? False { get; set; }
}
