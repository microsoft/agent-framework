// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.DependencyInjection;

namespace Hosted_Shared_Contributor_Setup;

/// <summary>
/// Registration helpers for the developer-only utilities shipped in this sample-shared project.
/// </summary>
public static class HostedContributorSetupExtensions
{
    /// <summary>
    /// Registers developer-only services that allow a hosted Foundry agent to run outside the
    /// Foundry platform (e.g., inside a Docker container during contributor debugging).
    ///
    /// <para><b>For local Docker debugging only and should not be used in production.</b></para>
    ///
    /// Currently this method registers a <see cref="DevTemporaryLocalSessionIsolationKeyProvider"/>
    /// so that requests succeed when the platform's <c>x-agent-user-isolation-key</c> and
    /// <c>x-agent-chat-isolation-key</c> headers are absent. In production those headers are
    /// always present and the default platform isolation key provider (registered automatically by
    /// the hosting layer) is used instead.
    /// </summary>
    /// <param name="services">The service collection to register the developer-only services into.</param>
    /// <returns>The same <see cref="IServiceCollection"/> for chaining.</returns>
    public static IServiceCollection AddDevTemporaryLocalContributorSetup(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton<HostedSessionIsolationKeyProvider, DevTemporaryLocalSessionIsolationKeyProvider>();
        return services;
    }
}
