// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;

namespace Microsoft.Agents.AI.Workflows.Declarative.Kit;

/// <summary>
/// Represents a session for supporting formula expressions within a workflow.
/// </summary>
public abstract class FormulaSession
{
    internal abstract WorkflowFormulaState State { get; }
}
