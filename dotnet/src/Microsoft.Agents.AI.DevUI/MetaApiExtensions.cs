// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DevUI.Entities;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Provides extension methods for mapping the server metadata endpoint to an <see cref="IEndpointRouteBuilder"/>.
/// </summary>
internal static class MetaApiExtensions
{
    /// <summary>
    /// Maps the HTTP API endpoint for retrieving server metadata.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the route to.</param>
    /// <param name="authRequired">Value reported via <c>auth_required</c> in the meta response so the frontend can decide whether to prompt for a bearer token.</param>
    /// <returns>The <see cref="IEndpointConventionBuilder"/> for method chaining.</returns>
    /// <remarks>
    /// This extension method registers the following endpoint:
    /// <list type="bullet">
    /// <item><description>GET /meta - Retrieve server metadata including UI mode, version, capabilities, and auth requirements</description></item>
    /// </list>
    /// The endpoint is compatible with the Python DevUI frontend and provides essential
    /// configuration information needed for proper frontend initialization.
    /// </remarks>
    public static IEndpointConventionBuilder MapMeta(this IEndpointRouteBuilder endpoints, bool authRequired = false)
    {
        return endpoints.MapGet("/meta", () => GetMeta(authRequired))
            .WithName("GetMeta")
            .WithSummary("Get server metadata and configuration")
            .WithDescription("Returns server metadata including UI mode, version, framework identifier, capabilities, and authentication requirements. Used by the frontend for initialization and feature detection.")
            .Produces<MetaResponse>(StatusCodes.Status200OK, contentType: "application/json");
    }

    private static IResult GetMeta(bool authRequired)
    {
        // TODO: Consider making these configurable via IOptions<DevUIOptions>
        // For now, using sensible defaults that match Python DevUI behavior

        var meta = new MetaResponse
        {
            UiMode = "developer", // Could be made configurable to support "user" mode
            Version = "0.1.0", // TODO: Extract from assembly version attribute
            Framework = "agent_framework",
            Runtime = "dotnet", // .NET runtime for deployment guides
            Capabilities = new Dictionary<string, bool>
            {
                // Tracing capability - will be enabled when trace event support is added
                ["tracing"] = false,

                // OpenAI proxy capability - not currently supported in .NET DevUI
                ["openai_proxy"] = false,

                // Deployment capability - not currently supported in .NET DevUI
                ["deployment"] = false
            },
            AuthRequired = authRequired
        };

        return Results.Json(meta, EntitiesJsonContext.Default.MetaResponse);
    }
}
