// Copyright (c) Microsoft. All rights reserved.

using System;
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
    /// Configures the host agent builder to use an in-memory session store for agent session management.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the in-memory session store.</param>
    /// <returns>The same <paramref name="builder"/> instance, configured to use an in-memory session store.</returns>
    public static IHostedAgentBuilder WithInMemorySessionStore(this IHostedAgentBuilder builder)
    {
        builder.ServiceCollection.AddKeyedSingleton<AgentSessionStore>(builder.Name, new InMemoryAgentSessionStore());
        return builder;
    }

    /// <summary>
    /// Registers the specified agent session store with the host agent builder, enabling session-specific storage for
    /// agent operations.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the session store. Cannot be null.</param>
    /// <param name="store">The agent session store instance to register. Cannot be null.</param>
    /// <returns>The same host agent builder instance, allowing for method chaining.</returns>
    public static IHostedAgentBuilder WithSessionStore(this IHostedAgentBuilder builder, AgentSessionStore store)
    {
        builder.ServiceCollection.AddKeyedSingleton(builder.Name, store);
        return builder;
    }

    /// <summary>
    /// Configures the host agent builder to use a custom session store implementation for agent sessions.
    /// </summary>
    /// <param name="builder">The host agent builder to configure.</param>
    /// <param name="createAgentSessionStore">A factory function that creates an agent session store instance using the provided service provider and agent
    /// name.</param>
    /// <param name="lifetime">The DI service lifetime for the session store registration. Defaults to <see cref="ServiceLifetime.Singleton"/>
    /// because session stores persist conversation state across requests and are consumed independently of the agent's lifetime.</param>
    /// <returns>The same host agent builder instance, enabling further configuration.</returns>
    public static IHostedAgentBuilder WithSessionStore(this IHostedAgentBuilder builder, Func<IServiceProvider, string, AgentSessionStore> createAgentSessionStore, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        builder.ServiceCollection.AddKeyedService(builder.Name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);
            return createAgentSessionStore(sp, keyString) ??
                throw new InvalidOperationException($"The agent session store factory did not return a valid {nameof(AgentSessionStore)} instance for key '{keyString}'.");
        }, lifetime);
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

        builder.ServiceCollection.AddKeyedSingleton(builder.Name, tool);

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

    /// <summary>
    /// Adds AI tool to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="factory">A factory function that creates a AI tool using the provided service provider.</param>
    /// <param name="lifetime">The DI service lifetime for the tool registration. If <see langword="null"/>, the agent's lifetime is used.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="factory"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the effective tool lifetime is shorter than the agent's lifetime, which would cause a captive dependency.
    /// For example, a singleton agent cannot use scoped or transient tools.
    /// </exception>
    public static IHostedAgentBuilder WithAITool(this IHostedAgentBuilder builder, Func<IServiceProvider, AITool> factory, ServiceLifetime? lifetime = null)
    {
        Throw.IfNull(builder);
        Throw.IfNull(factory);

        var effectiveLifetime = lifetime ?? builder.Lifetime;
        ValidateToolLifetime(builder.Lifetime, effectiveLifetime);

        builder.ServiceCollection.AddKeyedService(builder.Name, (sp, name) => factory(sp), effectiveLifetime);

        return builder;
    }

    /// <summary>
    /// Validates that the tool lifetime is compatible with the agent lifetime.
    /// A tool's lifetime must be at least as long as the agent's lifetime to prevent captive dependency issues.
    /// </summary>
    internal static void ValidateToolLifetime(ServiceLifetime agentLifetime, ServiceLifetime toolLifetime)
    {
        // ServiceLifetime enum: Singleton=0, Scoped=1, Transient=2
        // A higher value means a shorter lifetime.
        if (toolLifetime > agentLifetime)
        {
            throw new InvalidOperationException(
                $"A tool with lifetime '{toolLifetime}' cannot be registered for an agent with lifetime '{agentLifetime}'. " +
                "The tool's lifetime must be at least as long as the agent's lifetime to avoid captive dependency issues.");
        }
    }
}
