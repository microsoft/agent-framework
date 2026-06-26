// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Builder chained off <c>AddAgentFrameworkHost(...)</c>. Channel-add extension methods
/// (<c>AddResponsesChannel</c>, ...) hang off this interface.
/// </summary>
public interface IAgentFrameworkHostBuilder
{
    /// <summary>Underlying service collection.</summary>
    IServiceCollection Services { get; }

    /// <summary>Composition-time options.</summary>
    AgentFrameworkHostOptions Options { get; }

    /// <summary>Add a channel instance.</summary>
    IAgentFrameworkHostBuilder AddChannel(Channel channel);

    /// <summary>Add a channel resolved from DI via a factory.</summary>
    IAgentFrameworkHostBuilder AddChannel<TChannel>(Func<IServiceProvider, TChannel> factory) where TChannel : Channel;

    /// <summary>Replace the registered host state store.</summary>
    IAgentFrameworkHostBuilder UseHostStateStore<[DynamicallyAccessedMembers(DynamicallyAccessedMemberTypes.PublicConstructors)] TStore>()
        where TStore : class, IHostStateStore;
}
