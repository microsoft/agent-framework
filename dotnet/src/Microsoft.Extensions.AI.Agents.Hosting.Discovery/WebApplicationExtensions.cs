// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery;

/// <summary>
/// Provides extensions to enable agent discovery endpoints in a web application.
/// </summary>
public static class WebApplicationExtensions
{
    /// <summary>
    /// Enables the agent discovery endpoint at the specified path.
    /// </summary>
    public static void EnableDiscovery(this IEndpointRouteBuilder endpoints, string discoveryEndpoint = "/.well-known/agentframework/v1/agents")
    {
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.

        endpoints.MapGet(discoveryEndpoint, GetAgentsAsync);

#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

        // endpoints.MapGet(discoveryEndpoint + "/{agent}", GetAgentAsync);
    }

    private static IResult GetAgentsAsync(AgentDiscovery agentDiscovery, CancellationToken cancellationToken)
    {
        var agents = agentDiscovery.GetAllAgents();
        return Results.Ok(agents);
    }

    //private static async Task GetAgentAsync(string agent, HttpContext context)
    //{
    //}
}
