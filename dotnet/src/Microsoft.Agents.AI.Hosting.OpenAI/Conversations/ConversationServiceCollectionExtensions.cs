// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
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
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddInMemoryConversationStorage(this IServiceCollection services)
    {
        services.TryAddSingleton<IConversationStorage, InMemoryConversationStorage>();
        services.TryAddSingleton<IAgentConversationIndex, InMemoryAgentConversationIndex>();
        return services;
    }

    /// <summary>
    /// Adds conversation storage service to the service collection.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <returns>The service collection for chaining.</returns>
    internal static IServiceCollection AddConversationStorage<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TStorage>(this IServiceCollection services)
        where TStorage : class, IConversationStorage
    {
        services.TryAddSingleton<IConversationStorage, TStorage>();
        return services;
    }

    /// <summary>
    /// Adds an in-memory agent conversation index service to the service collection.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddInMemoryAgentConversationIndex(this IServiceCollection services)
    {
        services.TryAddSingleton<IAgentConversationIndex, InMemoryAgentConversationIndex>();
        return services;
    }

    /// <summary>
    /// Adds agent conversation index service to the service collection.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <returns>The service collection for chaining.</returns>
    internal static IServiceCollection AddAgentConversationIndex<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TIndex>(this IServiceCollection services)
        where TIndex : class, IAgentConversationIndex
    {
        services.TryAddSingleton<IAgentConversationIndex, TIndex>();
        return services;
    }
}
