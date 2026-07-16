// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.AGUI.AspNetCore;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Options;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure AG-UI support.
/// </summary>
public static class AGUIServerServiceCollectionExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via AG-UI.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddAGUIServer(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.TryAddEnumerable(ServiceDescriptor.Transient<IConfigureOptions<JsonOptions>, ConfigureAGUIJsonOptions>());

        return services;
    }
}
