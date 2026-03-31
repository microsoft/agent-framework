// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Responses;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Microsoft.Agents.AI.Hosting.AzureAIResponses;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to register the agent-framework
/// response handler with the Azure AI Responses Server SDK.
/// </summary>
public static class AgentFrameworkResponsesServiceCollectionExtensions
{
    /// <summary>
    /// Registers <see cref="AgentFrameworkResponseHandler"/> as the <see cref="ResponseHandler"/>
    /// for the Azure AI Responses Server SDK. Agents are resolved from keyed DI services
    /// using the <c>agent.name</c> or <c>metadata["entity_id"]</c> from incoming requests.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Call this method <b>after</b> <c>AddResponsesServer()</c> and after registering your
    /// <see cref="AIAgent"/> instances (e.g., via <c>AddAIAgent()</c>).
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddResponsesServer();
    /// builder.AddAIAgent("my-agent", ...);
    /// builder.Services.AddAgentFrameworkHandler();
    ///
    /// var app = builder.Build();
    /// app.MapResponsesServer();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddAgentFrameworkHandler(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Registers a specific <see cref="AIAgent"/> as the handler for all incoming requests,
    /// regardless of the <c>agent.name</c> in the request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload when hosting a single agent. The provided agent instance is
    /// registered both as a keyed service and as the default <see cref="AIAgent"/>.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddResponsesServer();
    /// builder.Services.AddAgentFrameworkHandler(myAgent);
    ///
    /// var app = builder.Build();
    /// app.MapResponsesServer();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="agent">The agent instance to register.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddAgentFrameworkHandler(this IServiceCollection services, AIAgent agent)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);

        services.TryAddSingleton(agent);
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }
}
