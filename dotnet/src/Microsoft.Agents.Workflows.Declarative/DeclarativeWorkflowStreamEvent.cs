// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that represents a streamed message produced by a declarative workflow.
/// </summary>
public class DeclarativeWorkflowStreamEvent(AgentRunResponseUpdate update) : DeclarativeWorkflowEvent(update)
{
    /// <summary>
    /// The streamed response data produced by the workflow, which is a <see cref="AgentRunResponseUpdate"/>.
    /// </summary>
    public new AgentRunResponseUpdate Data => update;
}
