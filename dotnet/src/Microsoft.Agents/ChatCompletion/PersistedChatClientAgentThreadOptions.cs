// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents;

/// <summary>
/// Contains configuration options for a <see cref="PersistedChatClientAgentThread"/>.
/// </summary>
public class PersistedChatClientAgentThreadOptions
{
    /// <summary>
    /// Gets or sets the maximum number of messages that will be used for an agent run.
    /// </summary>
    /// <remarks>
    /// If the number of messages in the thread exceeds this limit,
    /// only the most recent messages up t this limit will be used.
    /// </remarks>
    /// <value>20 if not set.</value>
    public int? MaxMessageCount { get; set; }
}
