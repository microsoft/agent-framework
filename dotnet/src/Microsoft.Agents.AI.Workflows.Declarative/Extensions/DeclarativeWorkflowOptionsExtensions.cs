// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.PowerFx;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class DeclarativeWorkflowOptionsExtensions
{
    private const int DefaultMaximumExpressionLength = 10000;

    public static RecalcEngine CreateRecalcEngine(this DeclarativeWorkflowOptions? context) =>
        RecalcEngineFactory.Create(context?.MaximumExpressionLength ?? DefaultMaximumExpressionLength, context?.MaximumCallDepth);
}
