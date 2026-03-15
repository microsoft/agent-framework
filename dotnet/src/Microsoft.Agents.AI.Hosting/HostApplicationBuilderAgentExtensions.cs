// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides extension methods for configuring AI agents in a host application builder.
/// </summary>
public static class HostApplicationBuilderAgentExtensions
{
    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name and instructions.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        Throw.IfNull(builder);
        return builder.Services.AddAIAgent(name, instructions, lifetime);
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClient">The chat client which the agent will use for inference.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, IChatClient chatClient, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.Services.AddAIAgent(name, instructions, chatClient, lifetime);
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="description">A description of the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If null, a non-keyed service will be resolved.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, string? description, object? chatClientServiceKey, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.Services.AddAIAgent(name, instructions, description, chatClientServiceKey, lifetime);
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If null, a non-keyed service will be resolved.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, object? chatClientServiceKey, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        Throw.IfNull(builder);
        return builder.Services.AddAIAgent(name, instructions, chatClientServiceKey, lifetime);
    }

    /// <summary>
    /// Adds an AI agent to the host application builder using a custom factory delegate.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="createAgentDelegate">A factory delegate that creates the AI agent instance. The delegate receives the service provider and agent key as parameters.</param>
    /// <param name="lifetime">The DI service lifetime for the agent registration. Defaults to <see cref="ServiceLifetime.Singleton"/>.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="createAgentDelegate"/> is null.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent factory delegate returns null or an invalid AI agent instance.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, Func<IServiceProvider, string, AIAgent> createAgentDelegate, ServiceLifetime lifetime = ServiceLifetime.Singleton)
    {
        Throw.IfNull(builder);
        return builder.Services.AddAIAgent(name, createAgentDelegate, lifetime);
    }
}
