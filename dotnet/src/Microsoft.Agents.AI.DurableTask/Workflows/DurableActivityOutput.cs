// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Output payload from activity execution, containing the result and other metadata.
/// </summary>
internal sealed class DurableActivityOutput
{
    /// <summary>
    /// Gets or sets the serialized result of the activity.
    /// </summary>
    public string? Result { get; set; }

    /// <summary>
    /// Gets or sets the collection of messages that have been sent.
    /// </summary>
    public List<SentMessageInfo> SentMessages { get; set; } = [];
}
