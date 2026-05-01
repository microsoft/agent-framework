// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.Reflection;
using Azure.AI.AgentServer.Responses;
using Azure.Core;
using Azure.Identity;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Shared.DiagnosticIds;
using OpenAI.Responses;

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
    /// builder.Services.AddKeyedSingleton&lt;AIAgent&gt;("my-agent", myAgent);
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
        services.TryAddSingleton<AgentSessionStore>(_ => FileSystemAgentSessionStore.CreateDefault());
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
    /// <param name="agentSessionStore">The agent session store to use for managing agent sessions server-side. If null, a file-system session store rooted at the agent home directory (or <c>{cwd}/.checkpoints</c> locally) will be used.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddFoundryResponses(this IServiceCollection services, AIAgent agent, AgentSessionStore? agentSessionStore = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(agent);

        services.AddResponsesServer();
        agentSessionStore ??= FileSystemAgentSessionStore.CreateDefault();

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
        return endpoints;
    }

    /// <summary>
    /// The ActivitySource name for the Responses hosting pipeline.
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
    /// Attempts to wrap the agent's underlying <see cref="ResponsesClient"/>
    /// with a <see cref="UserAgentResponsesClient"/> so every outgoing Responses-API request
    /// carries the hosted-agent <c>User-Agent</c> segment.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Best-effort and idempotent. The method is a no-op when:
    /// <list type="bullet">
    /// <item><description><paramref name="agent"/> exposes no <see cref="IChatClient"/>;</description></item>
    /// <item><description>the chat client is not backed by MEAI's internal <c>OpenAIResponsesChatClient</c> (e.g., a non-OpenAI provider or a custom impl);</description></item>
    /// <item><description>the inner <see cref="ResponsesClient"/> is already a <see cref="UserAgentResponsesClient"/>.</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// Works for any <see cref="ResponsesClient"/>-derived inner client — both the Foundry-specific
    /// <see cref="Azure.AI.Extensions.OpenAI.ProjectResponsesClient"/> and the native OpenAI
    /// <see cref="ResponsesClient"/> obtained from <see cref="OpenAI.OpenAIClient"/>. The wrapper preserves
    /// the inner client's pipeline (Transport, RetryPolicy, NetworkTimeout, OrganizationId / ProjectId /
    /// UserAgentApplicationId, custom policies) because every override delegates to the inner instance.
    /// </para>
    /// <para>
    /// Returns the same <paramref name="agent"/> instance unchanged. Mutation happens via
    /// reflection on MEAI's private <c>_responseClient</c> field; the agent itself is not wrapped.
    /// </para>
    /// </remarks>
    internal static AIAgent TryApplyUserAgent(AIAgent agent)
    {
        var chatClient = agent.GetService<IChatClient>();
        if (chatClient is null)
        {
            return agent;
        }

        var meaiType = s_meaiResponsesChatClientType;
        if (meaiType is null)
        {
            return agent;
        }

        var meaiInstance = chatClient.GetService(meaiType);
        if (meaiInstance is null)
        {
            return agent;
        }

        var field = s_meaiResponseClientField;
        if (field is null)
        {
            return agent;
        }

        var current = field.GetValue(meaiInstance) as ResponsesClient;
        if (current is null or UserAgentResponsesClient)
        {
            return agent;
        }

        field.SetValue(meaiInstance, new UserAgentResponsesClient(current));
        return agent;
    }

    /// <summary>
    /// MEAI's internal <c>OpenAIResponsesChatClient</c> type, resolved once via reflection.
    /// <see langword="null"/> if the type cannot be found (e.g., MEAI version drift).
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2026:RequiresUnreferencedCode",
        Justification = "MEAI's OpenAIResponsesChatClient is referenced through MicrosoftExtensionsAIResponsesExtensions and survives trimming.")]
    [UnconditionalSuppressMessage("Trimming", "IL2073:RequiresUnreferencedCode",
        Justification = "MEAI's OpenAIResponsesChatClient is referenced through MicrosoftExtensionsAIResponsesExtensions and survives trimming.")]
    private static readonly Type? s_meaiResponsesChatClientType =
        typeof(MicrosoftExtensionsAIResponsesExtensions).Assembly.GetType("Microsoft.Extensions.AI.OpenAIResponsesChatClient");

    /// <summary>
    /// MEAI's internal <c>_responseClient</c> field on <c>OpenAIResponsesChatClient</c>,
    /// resolved once via reflection. <see langword="null"/> if the field cannot be found.
    /// </summary>
    [UnconditionalSuppressMessage("Trimming", "IL2080:RequiresDynamicallyAccessedMembers",
        Justification = "OpenAIResponsesChatClient and its private fields are preserved by the polyfill design; MEAI does the same reflection internally.")]
    private static readonly FieldInfo? s_meaiResponseClientField =
        s_meaiResponsesChatClientType?.GetField("_responseClient", BindingFlags.NonPublic | BindingFlags.Instance);
}
