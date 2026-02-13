// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal interface IStatefulEdgeRunner
{
    ValueTask<PortableValue> ExportStateAsync();
    ValueTask ImportStateAsync(PortableValue state);
}

internal abstract class EdgeRunner
{
    // TODO: Can this be sync?
    protected internal abstract ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer);
}

internal abstract class EdgeRunner<TEdgeData>(
    IRunnerContext runContext, TEdgeData edgeData) : EdgeRunner()
{
    protected IRunnerContext RunContext { get; } = Throw.IfNull(runContext);
    protected TEdgeData EdgeData { get; } = Throw.IfNull(edgeData);

    protected Activity? StartActivity() => this.RunContext.TelemetryContext.StartEdgeGroupProcessActivity();
}
