// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// %%% COMMENT
/// </summary>
public class DeclarativeWorkflowStreamEvent(ChatResponseUpdate update) : DeclarativeWorkflowEvent(update)
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public new ChatResponseUpdate Data => update;
}
