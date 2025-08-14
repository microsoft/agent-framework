// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// %%% COMMENT
/// </summary>
public class DeclarativeWorkflowMessageEvent(ChatMessage message, UsageDetails? usage = null) : DeclarativeWorkflowEvent(message)
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public new ChatMessage Data => message;

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public UsageDetails? Usage => usage;
}
