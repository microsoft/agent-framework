// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.Http.Json;

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

        return services;
    }

    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via AG-UI with a custom agent resolver.
    /// </summary>
    /// <typeparam name="TResolver">The type of the agent resolver to register.</typeparam>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddAGUI<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TResolver>(this IServiceCollection services)
        where TResolver : class, IAGUIAgentResolver
    {
        ArgumentNullException.ThrowIfNull(services);

        services.AddAGUI();
        services.AddScoped<IAGUIAgentResolver, TResolver>();

        return services;
    }
}
