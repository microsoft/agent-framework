// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// %%% TODO
/// </summary>
public sealed class ExpressionContext
{
    internal ExpressionContext(WorkflowFormulaState state)
    {
        this.State = state;
    }

    internal WorkflowFormulaState State { get; }
}
