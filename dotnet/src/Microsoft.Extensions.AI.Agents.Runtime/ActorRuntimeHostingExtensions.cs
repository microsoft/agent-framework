// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides extension methods for configuring actor runtime services in a host application.
/// </summary>
public static class ActorRuntimeHostingExtensions
{
    /// <summary>
    /// Adds actor runtime services to the specified host application builder.
    /// </summary>
    /// <param name="builder">The <see cref="IHostApplicationBuilder"/> to configure.</param>
    /// <returns>An <see cref="IActorRuntimeBuilder"/> that can be used to further configure the actor runtime.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> is null.</exception>
    public static IActorRuntimeBuilder AddActorRuntime(this IHostApplicationBuilder builder) =>
        ActorRuntimeBuilder.GetOrAdd(builder);
}
