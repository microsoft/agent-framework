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
    /// <remarks>
    /// This method configures AG-UI JSON serialization, not authentication, authorization, or caller isolation.
    /// Multi-user hosts must configure ASP.NET Core authentication and authorization, require authorization
    /// on their <c>MapAGUIServer</c> endpoints, and register an <c>AgentIsolationKeyProvider</c> to isolate
    /// persisted sessions. For claims-based isolation, register <c>AddHttpContextAccessor()</c> and
    /// <c>UseClaimsBasedAgentIsolation(...)</c> from <c>Microsoft.Agents.AI.Hosting.AspNetCore</c>.
    /// </remarks>
    public static IServiceCollection AddAGUIServer(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.TryAddEnumerable(ServiceDescriptor.Transient<IConfigureOptions<JsonOptions>, ConfigureAGUIJsonOptions>());

        return services;
    }
}
