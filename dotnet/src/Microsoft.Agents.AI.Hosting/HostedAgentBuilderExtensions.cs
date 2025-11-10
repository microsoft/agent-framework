// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Hosting.Local;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring <see cref="AIAgent"/>.
/// </summary>
public static class HostedAgentBuilderExtensions
{
    /// <summary>
    /// Configures the host agent builder to use an in-memory thread store for agent thread management.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the in-memory thread store.</param>
    /// <returns>The same <paramref name="builder"/> instance, configured to use an in-memory thread store.</returns>
    public static IHostedAgentBuilder WithInMemoryThreadStore(this IHostedAgentBuilder builder)
    {
        builder.ServiceCollection.AddKeyedSingleton<AgentThreadStore>(builder.Name, new InMemoryAgentThreadStore());
        return builder;
    }

    /// <summary>
    /// Registers the specified agent thread store with the host agent builder, enabling thread-specific storage for
    /// agent operations.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the thread store. Cannot be null.</param>
    /// <param name="store">The agent thread store instance to register. Cannot be null.</param>
    /// <returns>The same host agent builder instance, allowing for method chaining.</returns>
    public static IHostedAgentBuilder WithThreadStore(this IHostedAgentBuilder builder, AgentThreadStore store)
    {
        builder.ServiceCollection.AddKeyedSingleton(builder.Name, store);
        return builder;
    }

    /// <summary>
    /// Configures the host agent builder to use a custom thread store implementation for agent threads.
    /// </summary>
    /// <param name="builder">The host agent builder to configure.</param>
    /// <param name="createAgentThreadStore">A factory function that creates an agent thread store instance using the provided service provider and agent
    /// name.</param>
    /// <returns>The same host agent builder instance, enabling further configuration.</returns>
    public static IHostedAgentBuilder WithThreadStore(this IHostedAgentBuilder builder, Func<IServiceProvider, string, AgentThreadStore> createAgentThreadStore)
    {
        builder.ServiceCollection.AddKeyedSingleton(builder.Name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);
            var store = createAgentThreadStore(sp, keyString);
            if (store is null)
            {
                throw new InvalidOperationException($"The agent thread store factory did not return a valid {nameof(AgentThreadStore)} instance for key '{keyString}'.");
            }

            return store;
        });
        return builder;
    }

    /// <summary>
    /// Adds an AI tool to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="tool">The AI tool to add to the agent.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="tool"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder WithAITool(this IHostedAgentBuilder builder, AITool tool)
    {
        Throw.IfNull(builder);
        Throw.IfNull(tool);

        var agentName = builder.Name;
        var services = builder.ServiceCollection;

        // Get or create the agent tool registry
        var descriptor = services.FirstOrDefault(sd => !sd.IsKeyedService && sd.ServiceType.Equals(typeof(LocalAgentToolRegistry)));
        if (descriptor?.ImplementationInstance is not LocalAgentToolRegistry toolRegistry)
        {
            toolRegistry = new();
            services.Add(ServiceDescriptor.Singleton(toolRegistry));
        }

        toolRegistry.AddTool(agentName, tool);

        return builder;
    }

    /// <summary>
    /// Adds multiple AI tools to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="tools">The collection of AI tools to add to the agent.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="tools"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder WithAITools(this IHostedAgentBuilder builder, params AITool[] tools)
    {
        Throw.IfNull(builder);
        Throw.IfNull(tools);

        foreach (var tool in tools)
        {
            builder.WithAITool(tool);
        }

        return builder;
    }
}
