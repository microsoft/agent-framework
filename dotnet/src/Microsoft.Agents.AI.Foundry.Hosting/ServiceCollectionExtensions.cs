// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Azure.Identity;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering agent-framework agents as Foundry Hosted Agents
/// using the Azure AI Responses Server SDK.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
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
        services.TryAddSingleton<AgentSessionStore, InMemoryAgentSessionStore>();
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
    /// <param name="agentSessionStore">The agent session store to use for managing agent sessions server-side. If null, an in-memory session store will be used.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, AIAgent agent, AgentSessionStore? agentSessionStore = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);

        services.AddResponsesServer();
        agentSessionStore ??= new InMemoryAgentSessionStore();

        if (!string.IsNullOrWhiteSpace(agent.Name))
        {
            services.TryAddKeyedSingleton(agent.Name, agent);
            services.TryAddKeyedSingleton(agent.Name, agentSessionStore);
        }

        // Also register as the default (non-keyed) agent so requests
        // without an agent name can resolve it (e.g., local dev tooling).
        services.TryAddSingleton(agent);
        services.TryAddSingleton(agentSessionStore);

        services.TryAddSingleton<ResponseHandler, AgentFrameworkResponseHandler>();
        return services;
    }

    /// <summary>
    /// Registers the Foundry Toolbox service, which eagerly connects to the Foundry Toolboxes
    /// MCP proxy at startup and provides MCP tools to <see cref="AgentFrameworkResponseHandler"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Each string in <paramref name="toolboxNames"/> is a toolbox name registered in the Foundry
    /// project. The proxy URL per toolbox is constructed as:
    /// <c>{FOUNDRY_AGENT_TOOLSET_ENDPOINT}/{toolboxName}/mcp?api-version=2025-05-01-preview</c>
    /// </para>
    /// <para>
    /// When <c>FOUNDRY_AGENT_TOOLSET_ENDPOINT</c> is absent, startup succeeds without error and
    /// no tools are loaded (the container remains healthy per spec §2).
    /// </para>
    /// <para>
    /// Example:
    /// <code>
    /// builder.Services.AddFoundryToolboxes("my-toolbox", "another-toolbox");
    /// </code>
    /// </para>
    /// </remarks>
    /// <param name="services">The service collection.</param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to connect to.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxes(
        this IServiceCollection services,
        params string[] toolboxNames)
        => services.AddFoundryToolboxes(configureOptions: null, toolboxNames);

    /// <summary>
    /// Registers the Foundry Toolbox service with additional options configuration.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <param name="configureOptions">Callback to further configure <see cref="FoundryToolboxOptions"/> (e.g. set <see cref="FoundryToolboxOptions.StrictMode"/>).</param>
    /// <param name="toolboxNames">Names of the Foundry toolboxes to pre-register at startup.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryToolboxes(
        this IServiceCollection services,
        Action<FoundryToolboxOptions>? configureOptions,
        params string[] toolboxNames)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<FoundryToolboxOptions>(opt =>
        {
            foreach (var name in toolboxNames)
            {
                if (!string.IsNullOrWhiteSpace(name))
                {
                    opt.ToolboxNames.Add(name);
                }
            }

            configureOptions?.Invoke(opt);
        });

        // Register DefaultAzureCredential as the default TokenCredential if not already registered
        services.TryAddSingleton<TokenCredential>(_ => new DefaultAzureCredential());

        // Register FoundryToolboxService as a singleton so it can be injected into the handler
        services.TryAddSingleton<FoundryToolboxService>();

        // AddHostedService uses TryAddEnumerable internally, so calling AddFoundryToolboxes
        // multiple times will not invoke StartAsync twice on the same singleton.
        services.AddHostedService(sp => sp.GetRequiredService<FoundryToolboxService>());

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

    /// <summary>
    /// The ActivitySource name for the Responses hosting pipeline.
    /// Matches the value previously exposed by <c>AgentHostTelemetry.ResponsesSourceName</c>
    /// in <c>Azure.AI.AgentServer.Core</c>.
    /// </summary>
    private const string ResponsesSourceName = "Azure.AI.AgentServer.Responses";

    /// <summary>
    /// Wraps <paramref name="agent"/> with <see cref="OpenTelemetryAgent"/> instrumentation
    /// so that agent invocations emit spans into the pipeline registered by
    /// <c>Azure.AI.AgentServer.Core</c>'s <c>AddAgentHostTelemetry()</c>.
    /// If the agent is already instrumented the original instance is returned unchanged.
    /// </summary>
    internal static AIAgent ApplyOpenTelemetry(AIAgent agent)
    {
        if (agent.GetService<OpenTelemetryAgent>() is not null)
        {
            return agent;
        }

        return agent.AsBuilder()
                    .UseOpenTelemetry(sourceName: ResponsesSourceName)
                    .Build();
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
