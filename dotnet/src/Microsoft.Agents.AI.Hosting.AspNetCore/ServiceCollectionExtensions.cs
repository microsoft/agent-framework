// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Extension methods for configuring AI hosting services in an <see cref="IServiceCollection"/>.
/// </summary>
public static class ServiceCollectionExtensions
{
    /// <summary>
    /// Registers a <see cref="SessionIsolationKeyProvider"/> that uses claims from the current user's identity
    /// to generate session isolation keys.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to add services to.</param>
    /// <param name="options"> Optional configuration for the claims-based session isolation key provider.</param>
    /// <returns>The <see cref="IServiceCollection"/> so that additional calls can be chained.</returns>
    /// <remarks>
    /// This method requires <see cref="IHttpContextAccessor"/> to be registered in the service collection.
    /// Ensure that <c>services.AddHttpContextAccessor()</c> has been called before using this method.
    /// </remarks>
    public static IServiceCollection UseClaimsBasedSessionIsolation(
        this IServiceCollection services,
        ClaimsIdentitySessionIsolationKeyProviderOptions? options = null)
    {
        options ??= new();
        ServiceDescriptor descriptor = new(typeof(SessionIsolationKeyProvider), CreateIsolationKeyProvider, ServiceLifetime.Singleton);
        services.Add(descriptor);

        return services;

        object CreateIsolationKeyProvider(IServiceProvider serviceProvider)
        {
            IHttpContextAccessor contextAccessor = serviceProvider.GetRequiredService<IHttpContextAccessor>();

            return new ClaimsIdentitySessionIsolationKeyProvider(contextAccessor, options);
        }
    }
}
