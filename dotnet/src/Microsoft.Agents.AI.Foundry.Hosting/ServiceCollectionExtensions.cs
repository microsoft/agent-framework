// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.Projects;
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
        SetHostedUserAgent();
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
        SetHostedUserAgent();

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
    /// Adds a pipeline policy to <paramref name="options"/> that appends the hosted-agent
    /// identifier (<c>foundry-hosting/agent-framework-dotnet/{version}</c>) to the
    /// <c>User-Agent</c> header on every outgoing HTTP request.
    /// </summary>
    /// <remarks>
    /// Call this method on the <see cref="AIProjectClientOptions"/> you pass to
    /// <see cref="AIProjectClient"/> so that outgoing API calls to Azure AI Foundry
    /// include the hosted-agent telemetry header.
    /// </remarks>
    /// <param name="options">The client options to configure.</param>
    /// <returns>The same <paramref name="options"/> instance for chaining.</returns>
    public static AIProjectClientOptions AddHostedAgentTelemetry(this AIProjectClientOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        options.AddPolicy(new HostedUserAgentPolicy(GetHostedUserAgentValue()), PipelinePosition.BeforeTransport);
        return options;
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

    /// <summary>
    /// Sets the global <see cref="HostedAgentContext.UserAgentSupplement"/> so that
    /// <c>MeaiUserAgentPolicy</c> in the Foundry package appends the hosted-agent
    /// identifier on code paths that use per-request <see cref="RequestOptions"/>.
    /// Called once at service registration time.
    /// </summary>
    private static void SetHostedUserAgent()
    {
        HostedAgentContext.UserAgentSupplement ??= GetHostedUserAgentValue();
    }

    /// <summary>
    /// Computes the <c>"foundry-hosting/agent-framework-dotnet/{version}"</c> string
    /// from the hosting assembly's informational version.
    /// </summary>
    private static string GetHostedUserAgentValue()
    {
        const string Name = "foundry-hosting/agent-framework-dotnet";

        if (typeof(FoundryHostingExtensions).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion is string version)
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

    /// <summary>Pipeline policy that appends the hosted-agent User-Agent segment to outgoing requests.</summary>
    private sealed class HostedUserAgentPolicy(string userAgentValue) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.AppendUserAgent(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.AppendUserAgent(message);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }

        private void AppendUserAgent(PipelineMessage message)
        {
            if (message.Request.Headers.TryGetValue("User-Agent", out var existing) && !string.IsNullOrEmpty(existing))
            {
                // Guard against double-appending on retries.
                if (!existing.Contains(userAgentValue, StringComparison.Ordinal))
                {
                    message.Request.Headers.Set("User-Agent", $"{existing} {userAgentValue}");
                }
            }
            else
            {
                message.Request.Headers.Set("User-Agent", userAgentValue);
            }
        }
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
