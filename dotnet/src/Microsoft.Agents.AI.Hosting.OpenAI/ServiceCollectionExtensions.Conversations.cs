// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for registering conversation services with the dependency injection container.
/// </summary>
public static class ConversationServiceCollectionExtensions
{
    /// <summary>
    /// Adds in-memory conversation storage and indexing services to the service collection.
    /// This is suitable for development and testing scenarios. For production, use a persistent storage implementation.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <param name="configureOptions">Optional action to configure <see cref="InMemoryStorageOptions"/>.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddOpenAIConversations(this IServiceCollection services, Action<InMemoryStorageOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(services);

        // Register storage options
        var storageOptions = new InMemoryStorageOptions();
        configureOptions?.Invoke(storageOptions);
        services.TryAddSingleton(storageOptions);

        services.TryAddSingleton<IConversationStorage, InMemoryConversationStorage>();
        services.TryAddSingleton<IAgentConversationIndex, InMemoryAgentConversationIndex>();
        return services;
    }
}
