// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Azure.AI.Projects;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Dependency-injection helpers that register a <see cref="FoundryMemoryProvider"/> wired with a
/// <see cref="HostedFoundryMemoryProviderScopes"/> strategy.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class HostedFoundryMemoryProviderServiceCollectionExtensions
{
    /// <summary>
    /// Registers a singleton <see cref="FoundryMemoryProvider"/> wired to the supplied
    /// <see cref="AIProjectClient"/> and the supplied <paramref name="stateInitializer"/>.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <param name="client">The <see cref="AIProjectClient"/> used to talk to Foundry Memory.</param>
    /// <param name="memoryStoreName">The name of the memory store in Microsoft Foundry.</param>
    /// <param name="stateInitializer">
    /// Strategy that selects the per-session <see cref="FoundryMemoryProviderScope"/>. When
    /// <see langword="null"/>, the extension uses <see cref="HostedFoundryMemoryProviderScopes.PerUser"/>.
    /// Pass any other helper (or a custom delegate) to override.
    /// </param>
    /// <param name="options">Optional <see cref="FoundryMemoryProviderOptions"/>.</param>
    /// <returns>The same <see cref="IServiceCollection"/> for chaining.</returns>
    public static IServiceCollection AddHostedFoundryMemoryProvider(
        this IServiceCollection services,
        AIProjectClient client,
        string memoryStoreName,
        Func<AgentSession?, FoundryMemoryProvider.State>? stateInitializer = null,
        FoundryMemoryProviderOptions? options = null)
    {
        Throw.IfNull(services);
        Throw.IfNull(client);
        Throw.IfNullOrWhitespace(memoryStoreName);

        var initializer = stateInitializer ?? HostedFoundryMemoryProviderScopes.PerUser();
        services.AddSingleton(sp => new FoundryMemoryProvider(
            client,
            memoryStoreName,
            initializer,
            options,
            sp.GetService<ILoggerFactory>()));
        return services;
    }

    /// <summary>
    /// Registers a singleton <see cref="FoundryMemoryProvider"/> that resolves its
    /// <see cref="AIProjectClient"/> from <see cref="IServiceProvider"/> at construction time.
    /// Use this overload when an <see cref="AIProjectClient"/> is already registered with the
    /// service collection.
    /// </summary>
    /// <param name="services">The service collection.</param>
    /// <param name="memoryStoreName">The name of the memory store in Microsoft Foundry.</param>
    /// <param name="stateInitializer">
    /// Strategy that selects the per-session <see cref="FoundryMemoryProviderScope"/>. When
    /// <see langword="null"/>, the extension uses <see cref="HostedFoundryMemoryProviderScopes.PerUser"/>.
    /// Pass any other helper (or a custom delegate) to override.
    /// </param>
    /// <param name="options">Optional <see cref="FoundryMemoryProviderOptions"/>.</param>
    /// <returns>The same <see cref="IServiceCollection"/> for chaining.</returns>
    public static IServiceCollection AddHostedFoundryMemoryProvider(
        this IServiceCollection services,
        string memoryStoreName,
        Func<AgentSession?, FoundryMemoryProvider.State>? stateInitializer = null,
        FoundryMemoryProviderOptions? options = null)
    {
        Throw.IfNull(services);
        Throw.IfNullOrWhitespace(memoryStoreName);

        var initializer = stateInitializer ?? HostedFoundryMemoryProviderScopes.PerUser();
        services.AddSingleton(sp => new FoundryMemoryProvider(
            sp.GetRequiredService<AIProjectClient>(),
            memoryStoreName,
            initializer,
            options,
            sp.GetService<ILoggerFactory>()));
        return services;
    }
}
