// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Adapts <see cref="FoundryToolboxService.StartupStatus"/> to the AspNetCore
/// HealthChecks pipeline so the <c>GET /readiness</c> probe (mapped by
/// <see cref="EndpointRouteBuilderExtensions.MapFoundryResponses"/>) reflects toolbox startup status,
/// not whether a toolbox is reachable: toolboxes are opened for each response, never at startup.
/// Pending uses the registration's failure status; Healthy and NoEndpoint report <c>Healthy</c>.
/// Registered automatically by
/// <see cref="ServiceCollectionExtensions.AddFoundryToolboxService(IServiceCollection, TokenCredential, string[])"/>
/// and its overloads.
/// </summary>
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
                    description: $"Foundry toolbox: {this._toolboxService.ToolboxNames.Count} toolbox(es) configured; each response opens its own toolbox connections."));

            case FoundryToolboxStartupStatus.NoEndpoint:
                return Task.FromResult(HealthCheckResult.Healthy(
                    description: "Foundry toolbox: neither FOUNDRY_PROJECT_ENDPOINT nor AZURE_AI_PROJECT_ENDPOINT is set; toolbox support disabled (local dev)."));

            case FoundryToolboxStartupStatus.Pending:
                return Task.FromResult(new HealthCheckResult(
                    status: context.Registration.FailureStatus,
                    description: "Foundry toolbox: startup has not completed yet."));

            default:
                return Task.FromResult(new HealthCheckResult(
                    status: context.Registration.FailureStatus,
                    description: $"Foundry toolbox: unknown startup status '{this._toolboxService.StartupStatus}'."));
        }
    }
}
