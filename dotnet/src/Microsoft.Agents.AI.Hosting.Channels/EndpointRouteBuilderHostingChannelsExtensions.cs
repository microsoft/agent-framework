// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Hosting.Channels;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Shared.Diagnostics;

#pragma warning disable IDE0130 // Namespace does not match folder structure - intentional: extension methods live in the host framework namespace.
namespace Microsoft.AspNetCore.Builder;
#pragma warning restore IDE0130

/// <summary>
/// Extension methods on <see cref="IEndpointRouteBuilder"/> for mounting an agent-framework host.
/// </summary>
public static class EndpointRouteBuilderHostingChannelsExtensions
{
    /// <summary>
    /// Mounts every registered channel's routes (rooted at each channel's path) and applies channel endpoint
    /// filters.
    /// </summary>
    public static IEndpointConventionBuilder MapAgentFrameworkHost(this IEndpointRouteBuilder endpoints)
    {
        Throw.IfNull(endpoints);

        var host = endpoints.ServiceProvider.GetRequiredService<AgentFrameworkHost>();
        var registry = endpoints.ServiceProvider.GetRequiredService<ChannelLifecycleRegistry>();
        var context = new ChannelContext(endpoints.ServiceProvider, host);
        var hostGroup = endpoints.MapGroup(string.Empty);

        // Lift Foundry-provided isolation headers into IsolationKeys.Current per request, but only when the
        // Foundry hosting environment flag is present. Absent the flag the raw headers are ignored.
        IEndpointFilter? isolationFilter = IsFoundryHostingEnvironment() ? new IsolationKeysEndpointFilter() : null;

        foreach (var channel in host.Channels)
        {
            var contribution = channel.Contribute(context);
            var channelGroup = string.IsNullOrEmpty(channel.Path) ? hostGroup : endpoints.MapGroup(channel.Path);

            registry.Add(contribution.OnStartup, contribution.OnShutdown);

            if (isolationFilter is not null)
            {
                channelGroup.AddEndpointFilter(isolationFilter);
            }

            foreach (var filter in contribution.EndpointFilters)
            {
                channelGroup.AddEndpointFilter(filter);
            }

            foreach (var register in contribution.Routes)
            {
                register(channelGroup);
            }
        }

        return hostGroup;
    }

    private static bool IsFoundryHostingEnvironment()
        => !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FOUNDRY_HOSTING_ENVIRONMENT"));
}
