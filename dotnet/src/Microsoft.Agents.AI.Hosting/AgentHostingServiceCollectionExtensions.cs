// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Hosting.Local;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring AI agents in a service collection.
/// </summary>
public static class AgentHostingServiceCollectionExtensions
{
    /// <summary>
    /// Adds an AI agent to the service collection using only a name and instructions, resolving the chat client from dependency injection.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <returns>The same <see cref="IServiceCollection"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="services"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IServiceCollection services, string name, string? instructions)
    {
        Throw.IfNull(services);
        Throw.IfNullOrEmpty(name);
        return services.AddAIAgent(name, (sp, key) =>
        {
            var chatClient = sp.GetRequiredService<IChatClient>();
            var tools = GetRegisteredToolsForAgent(sp, name);
            return new ChatClientAgent(chatClient, instructions, key, tools: tools);
        });
    }

    /// <summary>
    /// Adds an AI agent to the service collection with a provided chat client instance.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClient">The chat client which the agent will use for inference.</param>
    /// <returns>The same <see cref="IServiceCollection"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="services"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IServiceCollection services, string name, string? instructions, IChatClient chatClient)
    {
        Throw.IfNull(services);
        Throw.IfNullOrEmpty(name);
        return services.AddAIAgent(name, (sp, key) =>
        {
            var tools = GetRegisteredToolsForAgent(sp, name);
            return new ChatClientAgent(chatClient, instructions, key, tools: tools);
        });
    }

    /// <summary>
    /// Adds an AI agent to the service collection using a chat client resolved by an optional keyed service.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If <see langword="null"/>, a non-keyed service will be resolved.</param>
    /// <returns>The same <see cref="IServiceCollection"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="services"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IServiceCollection services, string name, string? instructions, object? chatClientServiceKey)
    {
        Throw.IfNull(services);
        Throw.IfNullOrEmpty(name);
        return services.AddAIAgent(name, (sp, key) =>
        {
            var chatClient = chatClientServiceKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientServiceKey);
            var tools = GetRegisteredToolsForAgent(sp, name);
            return new ChatClientAgent(chatClient, instructions, key, tools: tools);
        });
    }

    /// <summary>
    /// Adds an AI agent to the service collection using a chat client (optionally keyed) and a description.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="description">A description of the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If <see langword="null"/>, a non-keyed service will be resolved.</param>
    /// <returns>The same <see cref="IServiceCollection"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="services"/> or <paramref name="name"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IServiceCollection services, string name, string? instructions, string? description, object? chatClientServiceKey)
    {
        Throw.IfNull(services);
        Throw.IfNullOrEmpty(name);
        return services.AddAIAgent(name, (sp, key) =>
        {
            var chatClient = chatClientServiceKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientServiceKey);
            var tools = GetRegisteredToolsForAgent(sp, name);
            return new ChatClientAgent(chatClient, instructions: instructions, name: key, description: description, tools: tools);
        });
    }

    /// <summary>
    /// Adds an AI agent to the service collection using a custom factory delegate.
    /// </summary>
    /// <param name="services">The service collection to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="createAgentDelegate">A factory delegate that creates the AI agent instance. The delegate receives the service provider and agent key as parameters.</param>
    /// <returns>The same <see cref="IServiceCollection"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="services"/>, <paramref name="name"/>, or <paramref name="createAgentDelegate"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent factory delegate returns <see langword="null"/> or an agent whose <see cref="AIAgent.Name"/> does not match <paramref name="name"/>.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IServiceCollection services, string name, Func<IServiceProvider, string, AIAgent> createAgentDelegate)
    {
        Throw.IfNull(services);
        Throw.IfNull(name);
        Throw.IfNull(createAgentDelegate);
        services.AddKeyedSingleton(name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);
            var agent = createAgentDelegate(sp, keyString) ?? throw new InvalidOperationException($"The agent factory did not return a valid {nameof(AIAgent)} instance for key '{keyString}'.");
            if (!string.Equals(agent.Name, keyString, StringComparison.Ordinal))
            {
                throw new InvalidOperationException($"The agent factory returned an agent with name '{agent.Name}', but the expected name is '{keyString}'.");
            }

            return agent;
        });

        // Register the agent by name for discovery.
        var agentHostBuilder = GetAgentRegistry(services);
        agentHostBuilder.AgentNames.Add(name);

        return new HostedAgentBuilder(name, services);
    }

    private static LocalAgentRegistry GetAgentRegistry(IServiceCollection services)
    {
        var descriptor = services.FirstOrDefault(s => !s.IsKeyedService && s.ServiceType.Equals(typeof(LocalAgentRegistry)));
        if (descriptor?.ImplementationInstance is not LocalAgentRegistry instance)
        {
            instance = new LocalAgentRegistry();
            ConfigureHostBuilder(services, instance);
        }

        return instance;
    }

    private static void ConfigureHostBuilder(IServiceCollection services, LocalAgentRegistry agentHostBuilderContext)
    {
        services.Add(ServiceDescriptor.Singleton(agentHostBuilderContext));
        services.AddSingleton<AgentCatalog, LocalAgentCatalog>();
    }

    private static IList<AITool> GetRegisteredToolsForAgent(IServiceProvider serviceProvider, string agentName)
    {
        var registry = serviceProvider.GetService<LocalAgentToolRegistry>();
        return registry?.GetTools(agentName) ?? [];
    }
}
