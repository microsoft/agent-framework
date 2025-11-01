// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Purview.Models.Common;

/// <summary>
/// Base class to define DLP Actions.
/// </summary>
internal sealed class DlpActionInfo
{
    /// <summary>
    /// Gets or sets the name of the action. This would be a ToString of <see cref="DlpAction"/> enum.
    /// </summary>
    [JsonPropertyName("action")]
    public DlpAction Action { get; set; }

    /// <summary>
    /// The type of restriction action to take.
    /// </summary>
    [JsonPropertyName("restrictionAction")]
    public RestrictionAction? RestrictionAction { get; set; }
}
