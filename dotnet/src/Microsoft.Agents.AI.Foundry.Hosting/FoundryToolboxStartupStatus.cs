// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Outcome of <see cref="FoundryToolboxService"/> startup. Drives the
/// <c>foundry-toolbox</c> health-check that gates the <c>GET /readiness</c> probe so the
/// Foundry hosted runtime does not start routing traffic before pre-registered toolbox
/// connections are confirmed open (per <c>container-image-spec.md</c> §3.1).
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum FoundryToolboxStartupStatus
{
    /// <summary>
    /// <see cref="FoundryToolboxService.StartAsync"/> has not run yet. The health-check
    /// reports <c>Unhealthy</c> in this state so the platform waits for startup to
    /// complete before the first invocation.
    /// </summary>
    Pending = 0,

    /// <summary>
    /// Startup completed and either every pre-registered toolbox opened successfully or
    /// no pre-registered toolboxes were configured. The health-check reports
    /// <c>Healthy</c>.
    /// </summary>
    Healthy = 1,

    /// <summary>
    /// One or more pre-registered toolboxes failed to open during startup (including the
    /// partial case where some opened and some did not). The health-check reports
    /// <c>Unhealthy</c> and exposes the failed names in the <c>HealthCheckResult.Data</c>
    /// dictionary so operators can diagnose the failure without parsing log output.
    /// </summary>
    Unhealthy = 2,

    /// <summary>
    /// Neither the <c>FOUNDRY_PROJECT_ENDPOINT</c> nor the <c>AZURE_AI_PROJECT_ENDPOINT</c>
    /// environment variable is set. This is normal for local <c>dotnet run</c> flows and the
    /// health-check reports <c>Healthy</c> so the container is still routable; toolbox tools
    /// will simply not be available.
    /// </summary>
    NoEndpoint = 3,
}
