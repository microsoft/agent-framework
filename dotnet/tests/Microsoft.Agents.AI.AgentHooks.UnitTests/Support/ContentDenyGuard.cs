// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using AgentHooks;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

/// <summary>Denies at one point only when the projected context contains a marker string.</summary>
internal sealed class ContentDenyGuard(InterceptionPoint point, string marker) : IInterceptor
{
    public ValueTask<Verdict> InterceptAsync(AgentContext context, CancellationToken ct = default) =>
        context.InterceptionPoint == point && context.Json.ToJsonString().Contains(marker, StringComparison.Ordinal)
            ? new(Verdict.Deny("marker_blocked"))
            : new(Verdict.Allow);
}
