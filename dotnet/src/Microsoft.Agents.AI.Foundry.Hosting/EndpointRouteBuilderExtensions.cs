// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.AgentServer.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for mapping Foundry Responses endpoints.
/// </summary>
public static class EndpointRouteBuilderExtensions
{
    /// <summary>
    /// Maps the Responses API routes for the agent-framework handler to the endpoint routing pipeline.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Also maps the Foundry-required <c>GET /readiness</c> health probe to
    /// <see cref="HealthCheckEndpointRouteBuilderExtensions.MapHealthChecks(IEndpointRouteBuilder, string)"/>
    /// when no <c>/readiness</c> route is already registered. This makes the package
    /// spec-compliant in the Foundry hosted runtime (which probes <c>/readiness</c>
    /// before accepting any invocation per <c>container-image-spec.md</c> §2; without
    /// it every request fails with HTTP 424 <c>session_not_ready</c>) regardless of the
    /// host spine the developer chose:
    /// </para>
    /// <list type="bullet">
    ///   <item><description><b>Tier 1/2</b> (<c>AgentHost.CreateBuilder</c>) — the Core SDK
    ///         already maps <c>/readiness</c>. The duplicate-route guard below skips
    ///         re-mapping it.</description></item>
    ///   <item><description><b>Tier 3</b> (<c>WebApplication.CreateBuilder</c> +
    ///         <c>AddFoundryResponses</c> + <c>MapFoundryResponses</c>) — the Core SDK
    ///         does NOT map it. This call covers the gap automatically.</description></item>
    /// </list>
    /// <para>
    /// Developers can still opt out by registering their own <c>/readiness</c> route
    /// before calling <c>MapFoundryResponses</c>; the existing route is detected and
    /// preserved.
    /// </para>
    /// </remarks>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="prefix">Optional route prefix (e.g., "/openai/v1"). Default: empty (routes at /responses).</param>
    /// <returns>The endpoint route builder for chaining.</returns>
    public static IEndpointRouteBuilder MapFoundryResponses(this IEndpointRouteBuilder endpoints, string prefix = "")
    {
        _ = Throw.IfNull(endpoints);
        RouteGroupBuilder responsesEndpoints = endpoints.MapGroup(string.Empty);
        responsesEndpoints.AddEndpointFilter(new HostedProtocolCompatibilityFilter(
            endpoints.ServiceProvider.GetRequiredService<IConfiguration>(),
            endpoints.ServiceProvider.GetRequiredService<ILogger<HostedProtocolCompatibilityFilter>>()));
        responsesEndpoints.MapResponsesServer(prefix);
        MapReadinessIfMissing(endpoints);
        ServiceCollectionExtensions.MarkFeatureUsed();
        return endpoints;
    }

    /// <summary>
    /// Maps <c>GET /readiness</c> to the AspNetCore HealthChecks pipeline only when no
    /// route already serves that path. The duplicate guard scans
    /// <see cref="EndpointDataSource"/> entries by route pattern, which catches both the
    /// SDK-mapped <c>MapHealthChecks("/readiness")</c> path used by
    /// <c>AgentHostBuilder</c> and any user-registered <c>app.MapGet("/readiness", ...)</c>
    /// route. Idempotent across multiple <c>MapFoundryResponses</c> invocations.
    /// </summary>
    private static void MapReadinessIfMissing(IEndpointRouteBuilder endpoints)
    {
        const string ReadinessPath = "/readiness";

        foreach (var dataSource in endpoints.DataSources)
        {
            foreach (var endpoint in dataSource.Endpoints)
            {
                if (endpoint is RouteEndpoint route &&
                    string.Equals(route.RoutePattern.RawText, ReadinessPath, StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }
            }
        }

        endpoints.MapHealthChecks(ReadinessPath);
    }
}
