// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents a Noul question, a yes or no question whose answer is the probability of yes.
/// </summary>
/// <remarks>
/// The answer is a <see cref="JevNoulResponse"/>. A Noul needs <see cref="JevQuestion.Instructions"/>,
/// <see cref="Criteria"/>, or both. This type mirrors <c>NoulQuestion</c> of the official TypeSafe SDK.
/// </remarks>
[Description("A Noul question: a yes or no question whose answer is the probability of yes. Needs instructions, criteria, or both.")]
public sealed class JevNoulQuestion : JevQuestion
{
    /// <summary>
    /// Gets or sets optional descriptions of the yes and no outcomes.
    /// </summary>
    [JsonPropertyName("criteria")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [Description("Optional descriptions of the yes and no outcomes.")]
    public JevNoulCriteria? Criteria { get; set; }
}
