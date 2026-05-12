// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.DevUI;

/// <summary>
/// Provides helper methods for configuring the Microsoft Agents AI DevUI in ASP.NET applications.
/// </summary>
public static class DevUIExtensions
{
    /// <summary>
    /// Maps an endpoint that serves the DevUI from the '/devui' path.
    /// </summary>
    /// <remarks>
    /// <para>
    /// DevUI requires the OpenAI Responses and Conversations services to be registered with
    /// <see cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIResponses(IServiceCollection)"/> and
    /// <see cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIConversations(IServiceCollection)"/>,
    /// and the corresponding endpoints to be mapped using
    /// <see cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIResponses(IEndpointRouteBuilder)"/> and
    /// <see cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIConversations(IEndpointRouteBuilder)"/>.
    /// </para>
    /// <para>
    /// DevUI is restricted to loopback callers unless
    /// <see cref="DevUIOptions.AllowRemoteAccess"/> is set. See <see cref="DevUIOptions"/>
    /// for the available authentication and authorization hooks.
    /// </para>
    /// </remarks>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the endpoint to.</param>
    /// <returns>A <see cref="IEndpointConventionBuilder"/> that can be used to add authorization or other endpoint configuration.</returns>
    /// <seealso cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIResponses(IServiceCollection)"/>
    /// <seealso cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIConversations(IServiceCollection)"/>
    /// <seealso cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIResponses(IEndpointRouteBuilder)"/>
    /// <seealso cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIConversations(IEndpointRouteBuilder)"/>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="endpoints"/> is null.</exception>
    public static IEndpointConventionBuilder MapDevUI(
        this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);

        var authFilter = endpoints.ServiceProvider.GetRequiredService<DevUIAuthFilter>();
        var options = endpoints.ServiceProvider.GetRequiredService<IOptions<DevUIOptions>>().Value;
        var startupLogger = endpoints.ServiceProvider.GetRequiredService<ILogger<DevUIAuthFilter>>();

        WarnIfInsecurelyExposed(startupLogger, options);

        // /meta must remain reachable without authentication so the frontend can
        // discover whether a bearer token is required before prompting for one.
        endpoints.MapMeta(authRequired: authFilter.TokenRequired);

        var protectedGroup = endpoints.MapGroup("");

        // Conventions must be applied before endpoints are added to the group so
        // they reliably attach to every protected DevUI endpoint.
        options.ConfigureEndpoints?.Invoke(protectedGroup);
        protectedGroup.AddEndpointFilter(authFilter);

        protectedGroup.MapDevUI(pattern: "/devui");
        protectedGroup.MapEntities();

        return protectedGroup;
    }

    /// <summary>
    /// Maps an endpoint that serves the DevUI.
    /// </summary>
    /// <param name="endpoints">The <see cref="IEndpointRouteBuilder"/> to add the endpoint to.</param>
    /// <param name="pattern">
    /// The route pattern for the endpoint (e.g., "/devui", "/agent-ui").
    /// Defaults to "/devui" if not specified. This is the path where DevUI will be accessible.
    /// </param>
    /// <returns>A <see cref="IEndpointConventionBuilder"/> that can be used to add authorization or other endpoint configuration.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="endpoints"/> is null.</exception>
    /// <exception cref="ArgumentException">Thrown when <paramref name="pattern"/> is null or whitespace.</exception>
    internal static IEndpointConventionBuilder MapDevUI(
        this IEndpointRouteBuilder endpoints,
        [StringSyntax("Route")] string pattern = "/devui")
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        ArgumentException.ThrowIfNullOrWhiteSpace(pattern);

        // Ensure the pattern doesn't end with a slash for consistency
        var cleanPattern = pattern.TrimEnd('/');

        // Create the DevUI handler
        var logger = endpoints.ServiceProvider.GetRequiredService<ILogger<DevUIMiddleware>>();
        var devUIHandler = new DevUIMiddleware(logger, cleanPattern);

        return endpoints.MapGet($"{cleanPattern}/{{*path}}", devUIHandler.HandleRequestAsync)
            .WithName($"DevUI at {cleanPattern}")
            .WithDescription("Interactive developer interface for Microsoft Agent Framework");
    }

    private static void WarnIfInsecurelyExposed(ILogger logger, DevUIOptions options)
    {
        var tokenConfigured = !string.IsNullOrEmpty(options.AuthToken)
            || !string.IsNullOrEmpty(Environment.GetEnvironmentVariable(DevUIOptions.AuthTokenEnvironmentVariable));

        if (options.AllowRemoteAccess && !tokenConfigured && options.ConfigureEndpoints is null)
        {
            logger.LogWarning(
                "DevUI is configured with AllowRemoteAccess=true and no authentication. " +
                "Set DevUIOptions.AuthToken, the {EnvVar} environment variable, or attach an authorization policy via ConfigureEndpoints.",
                DevUIOptions.AuthTokenEnvironmentVariable);
        }
    }
}
