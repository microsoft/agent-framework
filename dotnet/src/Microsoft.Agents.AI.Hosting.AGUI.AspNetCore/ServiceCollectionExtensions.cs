// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure AG-UI support.
/// </summary>
public static class MicrosoftAgentAIHostingAGUIServiceCollectionExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via AG-UI.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddAGUI(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options => options.SerializerOptions.TypeInfoResolverChain.Add(AGUIJsonSerializerOptions.Default.TypeInfoResolver!));
        services.AddOptions<AGUIInMemorySessionStoreOptions>();
        services.TryAddSingleton<AgentSessionStore>(sp =>
            new AGUIInMemorySessionStore(sp.GetRequiredService<IOptions<AGUIInMemorySessionStoreOptions>>().Value));

        return services;
    }

    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via AG-UI and configures the default in-memory session store.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <param name="configureSessionStore">Configures the default <see cref="AGUIInMemorySessionStoreOptions"/>.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddAGUI(this IServiceCollection services, Action<AGUIInMemorySessionStoreOptions> configureSessionStore)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(configureSessionStore);

        services.AddAGUI();
        services.Configure(configureSessionStore);

        return services;
    }
}
