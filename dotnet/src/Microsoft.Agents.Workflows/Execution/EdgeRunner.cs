// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Execution;

internal abstract class EdgeRunner<TEdgeData>(
    IRunnerContext runContext, TEdgeData edgeData)
{
    protected IRunnerContext RunContext { get; } = Throw.IfNull(runContext);
    protected TEdgeData EdgeData { get; } = Throw.IfNull(edgeData);
}
