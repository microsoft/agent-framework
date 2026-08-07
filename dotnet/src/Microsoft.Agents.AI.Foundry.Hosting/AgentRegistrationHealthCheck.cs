// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Readiness health check that reports unhealthy until at least one <see cref="AIAgent"/> is
/// registered (as the default service or under any key). It is mapped onto the <c>/readiness</c>
/// probe by <see cref="FoundryHostingExtensions.MapFoundryResponses"/>, which the Foundry platform
/// calls before routing any request. Surfacing a missing-agent misconfiguration here turns what
/// would otherwise be a per-request failure (the handler cannot resolve an agent) into an early,
/// actionable not-ready signal.
/// </summary>
/// <remarks>
/// The check runs a predicate over the registered service descriptors, so it detects a keyed or
/// default registration without resolving (and therefore without constructing) any agent. It has
/// no side effects and is cheap to run on every readiness poll.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class AgentRegistrationHealthCheck : IHealthCheck
{
    private readonly Func<bool> _hasAnyAgent;

    public AgentRegistrationHealthCheck(Func<bool> hasAnyAgent)
    {
        ArgumentNullException.ThrowIfNull(hasAnyAgent);
        this._hasAnyAgent = hasAnyAgent;
    }

    public Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        if (this._hasAnyAgent())
        {
            return Task.FromResult(HealthCheckResult.Healthy(
                description: "Foundry agents: at least one AIAgent is registered."));
        }

        return Task.FromResult(new HealthCheckResult(
            status: context.Registration.FailureStatus,
            description: "Foundry agents: no AIAgent is registered. Register an agent via AddFoundryResponses(agent), or services.AddKeyedSingleton<AIAgent>(name, agent) followed by AddFoundryResponses()."));
    }
}
