// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Status of <see cref="FoundryToolboxService"/> startup, used by the
/// <c>foundry-toolbox</c> health check on the <c>GET /readiness</c> probe.
/// A healthy toolbox check does not guarantee that every pre-registered toolbox is available:
/// consent requirements and non-cancellation discovery failures are retained for per-request resolution.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public enum FoundryToolboxStartupStatus
{
    /// <summary>
    /// <see cref="FoundryToolboxService.StartAsync"/> has not completed. If checked in this state,
    /// the toolbox health check reports its registration's failure status
    /// (<c>Unhealthy</c> by default). Cancellation or an exception that escapes startup leaves
    /// this status unchanged; it is not converted to <see cref="Unhealthy"/>.
    /// </summary>
    Pending = 0,

    /// <summary>
    /// Startup completed and either every pre-registered toolbox opened successfully or
    /// no pre-registered toolboxes were configured. The health-check reports
    /// <c>Healthy</c>.
    /// </summary>
    Healthy = 1,

    /// <summary>
    /// <see cref="FoundryToolboxService.FailedToolboxNames"/> contains one or more names.
    /// The toolbox health check reports its registration's failure status (<c>Unhealthy</c>
    /// by default) and includes those names under <c>failedToolboxes</c> in
    /// <c>HealthCheckResult.Data</c>. The current service implementation does not populate
    /// that list: non-cancellation discovery failures are deferred instead, so normal startup
    /// does not produce this status.
    /// </summary>
    Unhealthy = 2,

    /// <summary>
    /// No project endpoint was resolved from the configured override or the
    /// <c>FOUNDRY_PROJECT_ENDPOINT</c> and <c>AZURE_AI_PROJECT_ENDPOINT</c> environment variables.
    /// Toolbox support is disabled. This is normal for local <c>dotnet run</c> flows,
    /// and the toolbox health check reports <c>Healthy</c>.
    /// </summary>
    NoEndpoint = 3,

    /// <summary>
    /// One or more pre-registered toolboxes could not enumerate their tools because a tool
    /// source requires user OAuth consent (the proxy returned <c>CONSENT_REQUIRED</c> at
    /// <c>tools/list</c> time). The health-check reports <c>Healthy</c> so the container stays
    /// routable: the consent requirement is surfaced to the caller as a per-request
    /// <c>oauth_consent_request</c>, and enumeration is retried once the user has consented.
    /// </summary>
    ConsentRequired = 4,

    /// <summary>
    /// One or more pre-registered toolboxes could not be enumerated at startup due to a non-consent,
    /// non-cancellation error, and no startup consent requirements are pending
    /// (otherwise the status is <see cref="ConsentRequired"/>). For example, a tool source may
    /// require a per-user delegated identity, which is only available on a user request's egress.
    /// The health-check reports <c>Healthy</c> so the container
    /// stays routable: the toolbox is retried per-request via
    /// <see cref="FoundryToolboxService.RetryDeferredToolboxesAsync"/>, where the per-user isolation key
    /// is present. A retry can resolve tools or surface a consent prompt for that response;
    /// other non-cancellation failures leave the toolbox deferred for later requests.
    /// </summary>
    Degraded = 5,
}
