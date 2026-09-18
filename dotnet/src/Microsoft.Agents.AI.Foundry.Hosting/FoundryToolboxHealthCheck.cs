// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Adapts <see cref="FoundryToolboxService.StartupStatus"/> to the AspNetCore
/// HealthChecks pipeline so the <c>GET /readiness</c> probe (mapped by
/// <see cref="FoundryHostingExtensions.MapFoundryResponses"/>) reflects whether
/// pre-registered toolbox connections are usable. Registered automatically by
/// <see cref="FoundryHostingExtensions.AddFoundryToolboxes(IServiceCollection, TokenCredential, string[])"/>
/// and its overloads.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal sealed class FoundryToolboxHealthCheck : IHealthCheck
{
    private readonly FoundryToolboxService _toolboxService;

    public FoundryToolboxHealthCheck(FoundryToolboxService toolboxService)
    {
        ArgumentNullException.ThrowIfNull(toolboxService);
        this._toolboxService = toolboxService;
    }

    public Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        switch (this._toolboxService.StartupStatus)
        {
            case FoundryToolboxStartupStatus.Healthy:
                return Task.FromResult(HealthCheckResult.Healthy(
                    description: $"Foundry toolbox: {this._toolboxService.Tools.Count} tool(s) available."));

            case FoundryToolboxStartupStatus.NoEndpoint:
                return Task.FromResult(HealthCheckResult.Healthy(
                    description: "Foundry toolbox: neither FOUNDRY_PROJECT_ENDPOINT nor AZURE_AI_PROJECT_ENDPOINT is set; toolbox support disabled (local dev)."));

            case FoundryToolboxStartupStatus.ConsentRequired:
                // Report Healthy so the container stays routable. The consent requirement is
                // surfaced to the caller per-request as an oauth_consent_request; enumeration is
                // retried once the user has consented. Do not include consent URLs here.
                return Task.FromResult(HealthCheckResult.Healthy(
                    description: $"Foundry toolbox: {this._toolboxService.ConsentRequiredToolboxNames.Count} pre-registered toolbox(es) awaiting user OAuth consent."));

            case FoundryToolboxStartupStatus.Degraded:
                // Report Healthy so the container stays routable. The toolbox could not be enumerated
                // at startup (no per-user context) and is retried per-request, where the platform
                // injects the per-user isolation key on egress.
                return Task.FromResult(HealthCheckResult.Healthy(
                    description: $"Foundry toolbox: {this._toolboxService.DeferredToolboxNames.Count} pre-registered toolbox(es) deferred to per-request resolution."));

            case FoundryToolboxStartupStatus.Pending:
                return Task.FromResult(new HealthCheckResult(
                    status: context.Registration.FailureStatus,
                    description: "Foundry toolbox: startup has not completed yet."));

            case FoundryToolboxStartupStatus.Unhealthy:
                var data = new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    ["failedToolboxes"] = this._toolboxService.FailedToolboxNames,
                };
                return Task.FromResult(new HealthCheckResult(
                    status: context.Registration.FailureStatus,
                    description: $"Foundry toolbox: {this._toolboxService.FailedToolboxNames.Count} pre-registered toolbox(es) failed to open at startup.",
                    data: data));

            default:
                return Task.FromResult(new HealthCheckResult(
                    status: context.Registration.FailureStatus,
                    description: $"Foundry toolbox: unknown startup status '{this._toolboxService.StartupStatus}'."));
        }
    }
}
