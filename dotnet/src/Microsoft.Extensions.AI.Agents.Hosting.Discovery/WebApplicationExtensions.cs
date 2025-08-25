// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
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
    [UnconditionalSuppressMessage("AOT", "IL3050:Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.", Justification = "<Pending>")]
    [RequiresUnreferencedCode("IL2026: Requres unreferenced code")]
    public static void EnableDiscovery(this IEndpointRouteBuilder endpoints, string discoveryEndpoint = "/.well-known/agentframework/v1/agents")
    {
        endpoints.MapGet(discoveryEndpoint, GetAgentDiscoveryAsync);
    }

    private static async Task<IResult> GetAgentDiscoveryAsync(AgentDiscovery discovery, CancellationToken cancellationToken)
    {
        return Results.Ok(discovery.GetAgentsMetadata());
    }
}
