// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// Represents the input of a Jev call: the state and the typed questions to answer about it.
/// </summary>
/// <remarks>
/// This type mirrors <c>SystemOneRequest</c> of the official TypeSafe SDK without the model, which the tool
/// configuration selects. Its JSON form is the argument shape of the <see cref="AIFunction"/> that
/// <see cref="JevAIToolBuilder"/> creates.
/// </remarks>
public sealed class JevRequest
{
    /// <summary>
    /// Gets or sets the content that the questions are about.
    /// </summary>
    /// <remarks>
    /// Text, or a JSON object or array for structured data, such as a conversation or related records. It mirrors
    /// <c>state</c> of <c>SystemOneRequest</c> in the official TypeSafe SDK, except that the API rejects
    /// <see cref="JevEntry.Null"/>.
    /// </remarks>
    [JsonPropertyName("state")]
    [Description("The content to answer questions about: text, or a JSON object or array for structured data. Questions can refer to object fields by name in backticks, for example `order`.")]
    public required JevEntry State { get; set; }

    /// <summary>
    /// Gets or sets the questions to answer, keyed by an ID that the caller chooses.
    /// </summary>
    /// <remarks>
    /// Each answer in <see cref="JevResult.Answers"/> uses the ID of its question.
    /// </remarks>
    [JsonPropertyName("questions")]
    [Description("The questions to answer about the state, keyed by an ID you choose. Each answer comes back under the same ID. Ask all related questions in one call.")]
    public required IReadOnlyDictionary<string, JevQuestion> Questions { get; set; }
}
