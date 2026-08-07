// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Extension methods for configuring AI hosting services in an <see cref="IServiceCollection"/>.
/// </summary>
public static class ServiceCollectionExtensions
{
    /// <summary>
    /// Registers an <see cref="AgentIsolationKeyProvider"/> that uses claims from the current user's identity
    /// to generate isolation keys for agent-owned resources.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to add services to.</param>
    /// <param name="options">Optional configuration for the claims-based isolation key provider.</param>
    /// <returns>The <see cref="IServiceCollection"/> so that additional calls can be chained.</returns>
    /// <remarks>
    /// <para>
    /// This method requires <see cref="IHttpContextAccessor"/> to be registered in the service collection.
    /// Ensure that <c>services.AddHttpContextAccessor()</c> has been called before using this method.
    /// </para>
    /// <para>
    /// When <paramref name="options"/> is not supplied, the isolation key is derived from the
    /// <see cref="ClaimTypes.NameIdentifier"/> claim, a stable unique subject identifier. For OpenID
    /// Connect tokens (including Microsoft Entra ID), this is typically mapped from the <c>sub</c> claim
    /// by the default JWT inbound claim mapping. Authentication schemes that do not project a unique
    /// identifier onto <see cref="ClaimTypes.NameIdentifier"/> (or hosts that require a different claim
    /// such as Entra's <c>oid</c>) should override
    /// <see cref="ClaimsIdentityAgentIsolationKeyProviderOptions.ClaimType"/>; otherwise the key may be
    /// absent, which causes strict-mode stores to fail.
    /// </para>
    /// <para>
    /// <strong>Security warning:</strong> If you override
    /// <see cref="ClaimsIdentityAgentIsolationKeyProviderOptions.ClaimType"/>, the chosen claim must
    /// uniquely identify the principal within the served population. Display names, usernames, email
    /// aliases, and other mutable or non-unique claims are <strong>unsafe</strong> isolation keys unless
    /// the host can prove their uniqueness across all callers, because distinct principals that share the
    /// same claim value would receive the same isolation key and could access one another's persisted data.
    /// </para>
    /// </remarks>
    public static IServiceCollection UseClaimsBasedAgentIsolation(
        this IServiceCollection services,
        ClaimsIdentityAgentIsolationKeyProviderOptions? options = null)
    {
        options ??= new();
        ServiceDescriptor descriptor = new(typeof(AgentIsolationKeyProvider), CreateIsolationKeyProvider, ServiceLifetime.Singleton);
        services.Add(descriptor);

        return services;

        object CreateIsolationKeyProvider(IServiceProvider serviceProvider)
        {
            IHttpContextAccessor contextAccessor = serviceProvider.GetRequiredService<IHttpContextAccessor>();

            return new ClaimsIdentityAgentIsolationKeyProvider(contextAccessor, options);
        }
    }
}
