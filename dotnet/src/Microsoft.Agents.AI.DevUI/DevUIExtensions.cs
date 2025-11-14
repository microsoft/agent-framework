// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

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
    /// DevUI requires the OpenAI Responses and Conversations services to be registered with
    /// <see cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIResponses(IServiceCollection)"/> and
    /// <see cref="MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions.AddOpenAIConversations(IServiceCollection)"/>,
    /// and the corresponding endpoints to be mapped using
    /// <see cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIResponses(IEndpointRouteBuilder)"/> and
    /// <see cref="MicrosoftAgentAIHostingOpenAIEndpointRouteBuilderExtensions.MapOpenAIConversations(IEndpointRouteBuilder)"/>.
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
        var group = endpoints.MapGroup("");
        group.MapDevUI(pattern: "/devui");
        group.MapMeta();
        group.MapEntities();
        return group;
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
}
