// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using AgentHooks;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>Returns a configured verdict at one interception point, allow elsewhere.</summary>
internal sealed class PointGuard(InterceptionPoint point, Verdict verdict) : IInterceptor
{
    public int Hits;

    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default)
    {
        if (context.InterceptionPoint == point)
        {
            Interlocked.Increment(ref this.Hits);
            return new(verdict);
        }

        return new(Verdict.Allow);
    }
}
