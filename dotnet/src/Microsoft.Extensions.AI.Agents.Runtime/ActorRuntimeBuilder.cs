// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Internal implementation of <see cref="IActorRuntimeBuilder"/> that manages actor type registrations
/// and their associated factory methods for the actor runtime system.
/// </summary>
internal sealed class ActorRuntimeBuilder : IActorRuntimeBuilder
{
    /// <summary>
    /// Gets the collection of registered actor types and their corresponding factory methods.
    /// </summary>
    /// <value>
    /// A dictionary where keys are <see cref="ActorType"/> instances and values are factory functions
    /// that create <see cref="IActor"/> instances given an <see cref="IServiceProvider"/> and <see cref="IActorRuntimeContext"/>.
    /// </value>
    public Dictionary<ActorType, Func<IServiceProvider, IActorRuntimeContext, IActor>> ActorFactories { get; } = [];

    /// <summary>
    /// Gets or creates an <see cref="ActorRuntimeBuilder"/> instance for the specified host application builder.
    /// If an instance already exists in the service collection, it returns the existing instance.
    /// Otherwise, it creates a new instance and registers it as a singleton service.
    /// </summary>
    /// <param name="builder">The host application builder to associate with the actor runtime builder.</param>
    /// <returns>
    /// An <see cref="ActorRuntimeBuilder"/> instance that can be used to configure actor types.
    /// </returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> is null.</exception>
    public static ActorRuntimeBuilder GetOrAdd(IHostApplicationBuilder builder)
    {
        Shared.Diagnostics.Throw.IfNull(builder);
        var services = builder.Services;
        var descriptor = services.FirstOrDefault(s => s.ImplementationInstance is ActorRuntimeBuilder);
        if (descriptor?.ImplementationInstance is not ActorRuntimeBuilder instance)
        {
            instance = new ActorRuntimeBuilder();
            services.Add(ServiceDescriptor.Singleton(instance));
            instance.ConfigureServices(services);
        }

        return instance;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ActorRuntimeBuilder"/> class.
    /// </summary>
    private ActorRuntimeBuilder()
    {
    }

    /// <summary>
    /// Registers an actor type with its factory method in the actor runtime.
    /// </summary>
    /// <param name="type">The actor type to register.</param>
    /// <param name="activator">
    /// The factory method that creates instances of the actor. This function receives an
    /// <see cref="IServiceProvider"/> for dependency injection and an <see cref="IActorRuntimeContext"/>
    /// for the actor's runtime context, and returns an <see cref="IActor"/> instance.
    /// </param>
    /// <exception cref="ArgumentException">
    /// Thrown when an actor type with the same name is already registered.
    /// </exception>
    /// <remarks>
    /// Each actor type can only be registered once. Attempting to register the same actor type
    /// multiple times will result in an exception being thrown by the underlying dictionary.
    /// </remarks>
    public void AddActorType(ActorType type, Func<IServiceProvider, IActorRuntimeContext, IActor> activator) =>
        this.ActorFactories.Add(type, activator);

    private void ConfigureServices(IServiceCollection services)
    {
        services.AddSingleton<IActorRuntimeBuilder>(this);
        services.AddSingleton<IActorStateStorage, InMemoryActorStateStorage>();
        services.AddSingleton<IActorClient, InProcessActorClient>();
        services.AddSingleton(sp =>
        {
            var actorStateStorage = sp.GetRequiredService<IActorStateStorage>();
            return new InProcessActorRuntime(sp, this.ActorFactories, actorStateStorage);
        });
    }
}
