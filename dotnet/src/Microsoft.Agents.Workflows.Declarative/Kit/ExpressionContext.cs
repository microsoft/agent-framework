// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// %%% TODO
/// </summary>
public sealed class ExpressionContext
{
    internal ExpressionContext(WorkflowScopes state)
    {
        this.State = state;
    }

    internal WorkflowScopes State { get; }
}
