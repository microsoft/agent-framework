// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.PowerFx;

/// <summary>
/// Base test class for PowerFx engine tests.
/// </summary>
public abstract class RecalcEngineTest(ITestOutputHelper output) : WorkflowTest(output)
{
    internal WorkflowFormulaState State { get; } = new(RecalcEngineFactory.Create());

    protected RecalcEngine Engine => this.State.Engine;
}
