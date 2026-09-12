// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>A context provider that registers an additional tool during run preparation.</summary>
internal sealed class ToolAddingContextProvider(AITool tool) : AIContextProvider
{
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        new(new AIContext { Tools = [tool] });
}
