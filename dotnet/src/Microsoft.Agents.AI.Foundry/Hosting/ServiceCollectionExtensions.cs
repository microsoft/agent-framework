// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering agent-framework agents as Foundry Hosted Agents
/// using the Azure AI Responses Server SDK.
/// </summary>
public static class FoundryHostingExtensions
{
    /// <summary>
    /// Registers the Azure AI Responses Server SDK and <see cref="AgentFrameworkResponseHandler"/>
    /// as the <see cref="ResponseHandler"/>. Agents are resolved from keyed DI services
    /// using the <c>agent.name</c> or <c>metadata["entity_id"]</c> from incoming requests.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method calls <c>AddResponsesServer()</c> internally, so you do not need to
    /// call it separately. Register your <see cref="AIAgent"/> instances before calling this.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.AddAIAgent("my-agent", ...);
    /// builder.Services.AddFoundryResponses();
    ///
    /// var app = builder.Build();
    /// app.MapFoundryResponses();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddResponsesServer();
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and a specific <see cref="AIAgent"/>
    /// as the handler for all incoming requests, regardless of the <c>agent.name</c> in the request.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Use this overload when hosting a single agent. The provided agent instance is
    /// registered as both a keyed service and the default <see cref="AIAgent"/>.
    /// This method calls <c>AddResponsesServer()</c> internally.
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddFoundryResponses(myAgent);
    ///
    /// var app = builder.Build();
    /// app.MapFoundryResponses();
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="agent">The agent instance to register.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, AIAgent agent)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);

        services.AddResponsesServer();
        services.TryAddSingleton(agent);
        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Maps the Responses API routes for the agent-framework handler to the endpoint routing pipeline.
    /// </summary>
    /// <param name="endpoints">The endpoint route builder.</param>
    /// <param name="prefix">Optional route prefix (e.g., "/openai/v1"). Default: empty (routes at /responses).</param>
    /// <returns>The endpoint route builder for chaining.</returns>
    public static IEndpointRouteBuilder MapFoundryResponses(this IEndpointRouteBuilder endpoints, string prefix = "")
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapResponsesServer(prefix);

        if (endpoints is IApplicationBuilder app)
        {
            // Ensure the middleware is added to the pipeline
            app.UseMiddleware<AgentFrameworkUserAgentMiddleware>();
        }

        return endpoints;
    }

    private sealed class AgentFrameworkUserAgentMiddleware(RequestDelegate next)
    {
        private static readonly string s_userAgentValue = CreateUserAgentValue();

        public async Task InvokeAsync(HttpContext context)
        {
            var headers = context.Request.Headers;
            var userAgent = headers.UserAgent.ToString();

            if (string.IsNullOrEmpty(userAgent))
            {
                headers.UserAgent = s_userAgentValue;
            }
            else if (!userAgent.Contains(s_userAgentValue, StringComparison.OrdinalIgnoreCase))
            {
                headers.UserAgent = $"{userAgent} {s_userAgentValue}";
            }

            await next(context).ConfigureAwait(false);
        }

        private static string CreateUserAgentValue()
        {
            const string Name = "agent-framework-dotnet";

            if (typeof(AgentFrameworkUserAgentMiddleware).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
            {
                int pos = version.IndexOf('+');
                if (pos >= 0)
                {
                    version = version.Substring(0, pos);
                }

                if (version.Length > 0)
                {
                    return $"{Name}/{version}";
                }
            }

            return Name;
        }
    }
}
