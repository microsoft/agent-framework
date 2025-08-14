// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that represents a streamed message produced by a declarative workflow.
/// </summary>
public class DeclarativeWorkflowStreamEvent(ChatResponseUpdate update) : DeclarativeWorkflowEvent(update)
{
    /// <summary>
    /// The streamed response data produced by the workflow, which is a <see cref="ChatResponseUpdate"/>.
    /// </summary>
    public new ChatResponseUpdate Data => update;
}
