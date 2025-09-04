// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.PowerFx;

/// <summary>
/// Base test class for PowerFx engine tests.
/// </summary>
public abstract class RecalcEngineTest(ITestOutputHelper output) : WorkflowTest(output)
{
    internal WorkflowScopes Scopes { get; } = new();

    protected RecalcEngine CreateEngine(int maximumExpressionLength = 500) => RecalcEngineFactory.Create(maximumExpressionLength);
}
