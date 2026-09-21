// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>Throws at one interception point, allow elsewhere (drives host_error:interceptor_failed).</summary>
internal sealed class CrashingGuard(InterceptionPoint point) : IInterceptor
{
    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default) =>
        context.InterceptionPoint == point
            ? throw new InvalidOperationException("guard crashed")
            : new(Verdict.Allow);
}
