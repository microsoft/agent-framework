// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring <see cref="AIAgent"/>.
/// </summary>
public static class HostedAgentBuilderExtensions
{
    /// <summary>
    /// Additionally registers the agent being configured as the default, non-keyed <see cref="AIAgent"/> service, so that it
    /// can be resolved without a service key.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when an earlier <see cref="AsDefault"/> call has already marked an agent as the default, including an
    /// earlier call on this same builder. Also thrown when the service collection contains no keyed
    /// <see cref="AIAgent"/> registration whose service key is <see cref="IHostedAgentBuilder.Name"/>, because the
    /// registration added here forwards to that keyed one. No descriptor is added when the exception is thrown.
    /// </exception>
    /// <remarks>
    /// <para>
    /// <see cref="AgentHostingServiceCollectionExtensions.AddAIAgent(IServiceCollection, string, string, ServiceLifetime)"/>
    /// and its overloads register the agent as a keyed service whose service key is the agent name. This method adds one
    /// additional, non-keyed <see cref="AIAgent"/> registration that forwards to the keyed one, using the agent's
    /// <see cref="IHostedAgentBuilder.Lifetime"/> and never invoking the agent factory independently, so a singleton agent
    /// resolves to the same instance both ways. The keyed registration is unaffected.
    /// </para>
    /// <para>
    /// Only registrations present when this method is called are checked, and only a second <see cref="AsDefault"/>
    /// call throws, on this builder or on any other. A non-keyed <see cref="AIAgent"/> registered earlier by other
    /// means is superseded by the registration added here under the usual last-registration-wins rule, and one
    /// registered afterwards supersedes this one. A TryAdd-style registration added afterwards (for example
    /// <c>AddFoundryResponses(services, agent)</c> from Microsoft.Agents.AI.Foundry.Hosting) is ignored, as is its
    /// keyed <see cref="AIAgent"/> registration under the same agent name, so <c>AsDefault()</c> wins over that call
    /// in either order. A keyed <see cref="AgentSessionStore"/> that such a call registers under the same agent name
    /// is not ignored: call <see cref="WithSessionStore(IHostedAgentBuilder, AgentSessionStore, bool)"/> if the
    /// default agent must not share it. Registering another keyed <see cref="AIAgent"/> under the same name after this
    /// call is not supported: the registration added here would forward to the replacement and, with a singleton
    /// lifetime, hold the first instance it resolves regardless of the replacement's lifetime.
    /// </para>
    /// <para>
    /// Use <see cref="ServiceLifetime.Singleton"/> for a default agent. Hosting integrations resolve it from the root
    /// provider, so a <see cref="ServiceLifetime.Scoped"/> agent fails scope validation or behaves as a singleton
    /// there, and a <see cref="ServiceLifetime.Transient"/> agent is created per request, loses the reference identity
    /// that keeps the keyed and non-keyed views of the agent de-duplicated and their session identity shared, and, if
    /// it is <see cref="IDisposable"/>, accumulates in the root scope.
    /// </para>
    /// <para>
    /// Under Microsoft.Agents.AI.Foundry.Hosting the default agent serves every request that names no agent and every
    /// request that names an unregistered agent, so do not mark a privileged agent as the default in a host that also
    /// serves untrusted callers. That host looks the agent's session store up by the agent name; a keyed store
    /// registered through <see cref="WithSessionStore(IHostedAgentBuilder, AgentSessionStore, bool)"/> is
    /// isolation-scoped and throws on use when no <see cref="AgentIsolationKeyProvider"/> is registered unless
    /// <c>withIsolation</c> is <see langword="false"/> or
    /// <see cref="IsolationKeyScopedAgentSessionStoreOptions.Strict"/> is disabled.
    /// </para>
    /// <para>
    /// If the agent implements <see cref="IDisposable"/> or <see cref="IAsyncDisposable"/>, the container disposes it
    /// through both registrations, so <see cref="IDisposable.Dispose"/> and <see cref="IAsyncDisposable.DisposeAsync"/>
    /// must be idempotent.
    /// </para>
    /// </remarks>
    public static IHostedAgentBuilder AsDefault(this IHostedAgentBuilder builder)
    {
        Throw.IfNull(builder);

        var services = builder.ServiceCollection;

        var hasKeyedAgentRegistration = false;
        foreach (var descriptor in services)
        {
            // ServiceDescriptor.ImplementationFactory and ImplementationInstance throw on keyed descriptors, so the
            // keyed check has to come first.
            if (descriptor.IsKeyedService)
            {
                if (!hasKeyedAgentRegistration && descriptor.ServiceType == typeof(AIAgent) && Equals(descriptor.ServiceKey, builder.Name))
                {
                    hasKeyedAgentRegistration = true;
                }

                continue;
            }

            // Only an earlier AsDefault() call is an error, because two of them are competing framework-owned claims on
            // the same slot. A non-keyed AIAgent registered by any other means is left alone: the descriptor added below
            // supersedes it under the standard last-registration-wins rule.
            if (descriptor.ServiceType == typeof(AIAgent) &&
                descriptor.ImplementationFactory?.Target is DefaultAgentFactory existingDefaultAgentFactory)
            {
                throw new InvalidOperationException(
                    CreateDuplicateDefaultAgentMessage(builder.Name, existingDefaultAgentFactory.Name));
            }
        }

        if (!hasKeyedAgentRegistration)
        {
            // The forwarding registration below would otherwise fail only at resolution time, and where DevUI's
            // KeyedService.AnyKey agent factory is registered the two factories would call each other instead.
            throw new InvalidOperationException(
                $"No keyed {nameof(AIAgent)} registration exists for agent '{builder.Name}'; " +
                $"call {nameof(AsDefault)}() on the builder returned by AddAIAgent or AddAsAIAgent.");
        }

        // Forwarding to the keyed registration keeps a single instance per lifetime scope and ensures the agent factory is
        // never invoked independently of the keyed path. The forwarding delegate is an instance method of a named type so
        // that a later AsDefault() call can recover the agent name from the descriptor.
        var defaultAgentFactory = new DefaultAgentFactory(builder.Name);
        services.Add(new ServiceDescriptor(typeof(AIAgent), defaultAgentFactory.Resolve, builder.Lifetime));

        return builder;
    }

    /// <summary>
    /// Configures the host agent builder to use an in-memory session store for agent session management.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the in-memory session store.</param>
    /// <param name="withIsolation">When <see langword="true"/>, wraps the session store with an <see cref="IsolationKeyScopedAgentSessionStore"/>
    /// that adds a partition from <see cref="AgentIsolationKeyProvider"/>. Defaults to <see langword="true"/>.</param>
    /// <returns>The same <paramref name="builder"/> instance, configured to use an in-memory session store.</returns>
    public static IHostedAgentBuilder WithInMemorySessionStore(this IHostedAgentBuilder builder, bool withIsolation = true)
        => builder.WithSessionStore(new InMemoryAgentSessionStore(), withIsolation);

    /// <summary>
    /// Registers the specified agent session store with the host agent builder, enabling session-specific storage for
    /// agent operations.
    /// </summary>
    /// <param name="builder">The host agent builder to configure with the session store. Cannot be null.</param>
    /// <param name="store">The agent session store instance to register. Cannot be null.</param>
    /// <param name="withIsolation">When <see langword="true"/>, wraps the session store with an <see cref="IsolationKeyScopedAgentSessionStore"/>
    /// that adds a partition from <see cref="AgentIsolationKeyProvider"/>. Defaults to <see langword="true"/>.</param>
    /// <returns>The same host agent builder instance, allowing for method chaining.</returns>
    public static IHostedAgentBuilder WithSessionStore(this IHostedAgentBuilder builder, AgentSessionStore store, bool withIsolation = true)
        => builder.WithSessionStore((sp, key) => store, ServiceLifetime.Singleton, withIsolation);

    /// <summary>
    /// Configures the host agent builder to use a custom session store implementation for agent sessions.
    /// </summary>
    /// <param name="builder">The host agent builder to configure.</param>
    /// <param name="createAgentSessionStore">A factory function that creates an agent session store instance using the provided service provider and agent
    /// name.</param>
    /// <param name="lifetime">The DI service lifetime for the session store registration. Defaults to <see cref="ServiceLifetime.Singleton"/>
    /// because session stores persist conversation state across requests and are consumed independently of the agent's lifetime.</param>
    /// <param name="withIsolation">When <see langword="true"/>, wraps the session store with an <see cref="IsolationKeyScopedAgentSessionStore"/>
    /// that adds a partition from <see cref="AgentIsolationKeyProvider"/>. Defaults to <see langword="true"/>.</param>
    /// <returns>The same host agent builder instance, enabling further configuration.</returns>
    public static IHostedAgentBuilder WithSessionStore(this IHostedAgentBuilder builder, Func<IServiceProvider, string, AgentSessionStore> createAgentSessionStore, ServiceLifetime lifetime = ServiceLifetime.Singleton, bool withIsolation = true)
    {
        builder.ServiceCollection.AddKeyedService(builder.Name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);

            AgentSessionStore store = createAgentSessionStore(sp, keyString) ??
                throw new InvalidOperationException($"The agent session store factory did not return a valid {nameof(AgentSessionStore)} instance for key '{keyString}'.");

            if (withIsolation && store.GetService<IsolationKeyScopedAgentSessionStore>() is null)
            {
                var isolationKeyProvider = sp.GetService<AgentIsolationKeyProvider>();

                // Best efforts options getting
                IsolationKeyScopedAgentSessionStoreOptions? options = sp.GetService<IsolationKeyScopedAgentSessionStoreOptions>();
                if (options is null)
                {
                    var optionsProvider = sp.GetService<IOptions<IsolationKeyScopedAgentSessionStoreOptions>>();
                    options = optionsProvider?.Value;
                }

                store = new IsolationKeyScopedAgentSessionStore(store, isolationKeyProvider, options ?? new());
            }

            return store;
        }, lifetime);
        return builder;
    }

    /// <summary>
    /// Adds an AI tool to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="tool">The AI tool to add to the agent.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="tool"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder WithAITool(this IHostedAgentBuilder builder, AITool tool)
    {
        Throw.IfNull(builder);
        Throw.IfNull(tool);

        builder.ServiceCollection.AddKeyedSingleton(builder.Name, tool);

        return builder;
    }

    /// <summary>
    /// Adds multiple AI tools to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="tools">The collection of AI tools to add to the agent.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="tools"/> is <see langword="null"/>.</exception>
    public static IHostedAgentBuilder WithAITools(this IHostedAgentBuilder builder, params AITool[] tools)
    {
        Throw.IfNull(builder);
        Throw.IfNull(tools);

        foreach (var tool in tools)
        {
            builder.WithAITool(tool);
        }

        return builder;
    }

    /// <summary>
    /// Adds AI tool to an agent being configured with the service collection.
    /// </summary>
    /// <param name="builder">The hosted agent builder.</param>
    /// <param name="factory">A factory function that creates a AI tool using the provided service provider.</param>
    /// <param name="lifetime">The DI service lifetime for the tool registration. If <see langword="null"/>, the agent's lifetime is used.</param>
    /// <returns>The same <see cref="IHostedAgentBuilder"/> instance so that additional calls can be chained.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/> or <paramref name="factory"/> is <see langword="null"/>.</exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the effective tool lifetime is shorter than the agent's lifetime, which would cause a captive dependency.
    /// For example, a singleton agent cannot use scoped or transient tools.
    /// </exception>
    public static IHostedAgentBuilder WithAITool(this IHostedAgentBuilder builder, Func<IServiceProvider, AITool> factory, ServiceLifetime? lifetime = null)
    {
        Throw.IfNull(builder);
        Throw.IfNull(factory);

        var effectiveLifetime = lifetime ?? builder.Lifetime;
        ValidateToolLifetime(builder.Lifetime, effectiveLifetime);

        builder.ServiceCollection.AddKeyedService(builder.Name, (sp, name) => factory(sp), effectiveLifetime);

        return builder;
    }

    /// <summary>
    /// Validates that the tool lifetime is compatible with the agent lifetime.
    /// A tool's lifetime must be at least as long as the agent's lifetime to prevent captive dependency issues.
    /// </summary>
    internal static void ValidateToolLifetime(ServiceLifetime agentLifetime, ServiceLifetime toolLifetime)
    {
        // ServiceLifetime enum: Singleton=0, Scoped=1, Transient=2
        // A higher value means a shorter lifetime.
        if (toolLifetime > agentLifetime)
        {
            throw new InvalidOperationException(
                $"A tool with lifetime '{toolLifetime}' cannot be registered for an agent with lifetime '{agentLifetime}'. " +
                "The tool's lifetime must be at least as long as the agent's lifetime to avoid captive dependency issues.");
        }
    }

    /// <summary>
    /// Builds the message of the <see cref="InvalidOperationException"/> thrown when <see cref="AsDefault"/> is called
    /// while an agent has already been marked as the default. Both branches quote the agent being marked.
    /// </summary>
    private static string CreateDuplicateDefaultAgentMessage(string name, string existingDefaultAgentName)
        => string.Equals(name, existingDefaultAgentName, StringComparison.Ordinal)
            ? $"{nameof(AsDefault)}() has already been called for agent '{name}'."
            : $"Cannot register agent '{name}' as the default agent because agent '{existingDefaultAgentName}' has already been marked as the default with {nameof(AsDefault)}(). " +
                $"Only one agent can be the default. Call {nameof(AsDefault)}() on only one agent.";

    /// <summary>
    /// Resolves the keyed <see cref="AIAgent"/> registration that a default (non-keyed) registration forwards to, and
    /// carries the agent name so a later <see cref="AsDefault"/> call can report which agent is already the default.
    /// </summary>
    private sealed class DefaultAgentFactory(string name)
    {
        public string Name { get; } = name;

        public AIAgent Resolve(IServiceProvider serviceProvider) => serviceProvider.GetRequiredKeyedService<AIAgent>(this.Name);
    }
}
