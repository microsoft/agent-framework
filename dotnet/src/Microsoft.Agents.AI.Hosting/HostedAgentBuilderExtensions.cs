// Copyright (c) Microsoft. All rights reserved.

using System;
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
}
