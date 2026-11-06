// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Extension methods for registering Foundry Responses hosting on an <see cref="IHostApplicationBuilder"/>.
/// </summary>
public static class HostApplicationBuilderExtensions
{
    /// <summary>
    /// Registers the Azure AI Responses Server SDK and the Agent Framework response handler
    /// on a host application builder.
    /// </summary>
    /// <remarks>
    /// Use this overload for applications that can access their host builder. In a Foundry hosted
    /// environment it binds the response-storage and resilient-task-storage identity and endpoint
    /// from the same <c>ResponsesServer</c> configuration section, as required by AgentServer.
    /// <code>
    /// builder.Services.AddKeyedSingleton&lt;AIAgent&gt;("my-agent", myAgent);
    /// builder.AddFoundryResponses();
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        FoundryResponsesOptions? options = null)
    {
        _ = Throw.IfNull(host);
        FoundryResponsesOptions configuredOptions = ResolveFoundryResponsesOptions(host, options);
        bool serverAdded = ServiceCollectionExtensions.AddResponsesServerOnce(
            host.Services,
            host,
            configuredOptions,
            options is not null);
        host.Services.AddHealthChecks();
        ServiceCollectionExtensions.ConfigureFoundryListenPort(host.Services);
        ServiceCollectionExtensions.ConfigureFoundryResponsesOptions(
            host.Services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
        host.Services.TryAddSingleton<AgentSessionStore>(_ => ServiceCollectionExtensions.CreateDefaultAgentSessionStore());
        ServiceCollectionExtensions.RegisterResponseHandler(host.Services);
        ServiceCollectionExtensions.MarkFeatureUsed();
        return host;
    }

    /// <summary>
    /// Registers the Azure AI Responses Server SDK and a specific <see cref="AIAgent"/> on a host
    /// application builder.
    /// </summary>
    /// <remarks>
    /// <code>
    /// builder.AddFoundryResponses(myAgent);
    /// </code>
    /// </remarks>
    /// <param name="host">The host application builder.</param>
    /// <param name="agent">The agent instance to register.</param>
    /// <param name="agentSessionStore">The agent session store to use, or <see langword="null"/> for the default.</param>
    /// <param name="options">Optional hosting behavior. Required inputs belong on the extension method parameters.</param>
    /// <returns>The host application builder for chaining.</returns>
    public static IHostApplicationBuilder AddFoundryResponses(
        this IHostApplicationBuilder host,
        AIAgent agent,
        AgentSessionStore? agentSessionStore = null,
        FoundryResponsesOptions? options = null)
    {
        _ = Throw.IfNull(host);
        _ = Throw.IfNull(agent);

        FoundryResponsesOptions configuredOptions = ResolveFoundryResponsesOptions(host, options);
        bool serverAdded = ServiceCollectionExtensions.AddResponsesServerOnce(
            host.Services,
            host,
            configuredOptions,
            options is not null);
        host.Services.AddHealthChecks();
        ServiceCollectionExtensions.ConfigureFoundryListenPort(host.Services);
        ServiceCollectionExtensions.ConfigureFoundryResponsesOptions(
            host.Services,
            configuredOptions,
            includeServerOptions: serverAdded,
            applyOptions: serverAdded || options is not null);
        agentSessionStore ??= ServiceCollectionExtensions.CreateDefaultAgentSessionStore();

        if (!string.IsNullOrWhiteSpace(agent.Name))
        {
            host.Services.TryAddKeyedSingleton(agent.Name, agent);
            host.Services.TryAddKeyedSingleton(agent.Name, agentSessionStore);
        }

        host.Services.TryAddSingleton(agent);
        host.Services.TryAddSingleton(agentSessionStore);

        ServiceCollectionExtensions.RegisterResponseHandler(host.Services);
        ServiceCollectionExtensions.MarkFeatureUsed();
        return host;
    }

    private static FoundryResponsesOptions ResolveFoundryResponsesOptions(
        IHostApplicationBuilder host,
        FoundryResponsesOptions? suppliedOptions)
    {
        if (suppliedOptions is not null)
        {
            // AgentServer applies code configuration after host configuration. A supplied options
            // object follows the same contract, including its inherited AgentServer defaults.
            return ServiceCollectionExtensions.CopyFoundryResponsesOptions(suppliedOptions);
        }

        FoundryResponsesOptions options = new();
        IConfigurationSection section =
            host.Configuration.GetSection(ServiceCollectionExtensions.ResponsesServerSettingsSectionName);
        options.DefaultModel = section[nameof(FoundryResponsesOptions.DefaultModel)];
        if (int.TryParse(
            section[nameof(FoundryResponsesOptions.DefaultFetchHistoryCount)],
            out int defaultFetchHistoryCount))
        {
            options.DefaultFetchHistoryCount = defaultFetchHistoryCount;
        }

        if (bool.TryParse(section[nameof(FoundryResponsesOptions.ResilientBackground)], out bool resilientBackground))
        {
            options.ResilientBackground = resilientBackground;
        }

        if (bool.TryParse(section[nameof(FoundryResponsesOptions.SteerableConversations)], out bool steerableConversations))
        {
            options.SteerableConversations = steerableConversations;
        }

        return options;
    }
}
