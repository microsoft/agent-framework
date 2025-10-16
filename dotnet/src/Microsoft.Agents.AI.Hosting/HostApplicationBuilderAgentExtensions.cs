// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using Microsoft.Agents.AI.Hosting.Local;
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
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.AddAIAgent(name, instructions, chatClientServiceKey: null);
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClient">The chat client which the agent will use for inference.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, IChatClient chatClient)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.AddAIAgent(name, (sp, key) => new ChatClientAgent(chatClient, instructions, key));
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="description">A description of the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If null, a non-keyed service will be resolved.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, string? description, object? chatClientServiceKey)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.AddAIAgent(name, (sp, key) =>
        {
            var chatClient = chatClientServiceKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientServiceKey);
            return new ChatClientAgent(chatClient, instructions: instructions, name: key, description: description);
        });
    }

    /// <summary>
    /// Adds an AI agent to the host application builder with the specified name, instructions, and chat client key.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="chatClientServiceKey">The key to use when resolving the chat client from the service provider. If null, a non-keyed service will be resolved.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="instructions"/> is null.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string? instructions, object? chatClientServiceKey)
    {
        Throw.IfNull(builder);
        Throw.IfNullOrEmpty(name);
        return builder.AddAIAgent(name, (sp, key) =>
        {
            var chatClient = chatClientServiceKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientServiceKey);
            return new ChatClientAgent(chatClient, instructions, key);
        });
    }

    /// <summary>
    /// Adds an AI agent to the host application builder using a custom factory delegate.
    /// </summary>
    /// <param name="builder">The host application builder to configure.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="createAgentDelegate">A factory delegate that creates the AI agent instance. The delegate receives the service provider and agent key as parameters.</param>
    /// <returns>The configured host application builder.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="builder"/>, <paramref name="name"/>, or <paramref name="createAgentDelegate"/> is null.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the agent factory delegate returns null or an invalid AI agent instance.</exception>
    public static IHostedAgentBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, Func<IServiceProvider, string, AIAgent> createAgentDelegate)
    {
        Throw.IfNull(builder);
        Throw.IfNull(name);
        Throw.IfNull(createAgentDelegate);
        builder.Services.AddKeyedSingleton(name, (sp, key) =>
        {
            Throw.IfNull(key);
            var keyString = key as string;
            Throw.IfNullOrEmpty(keyString);
            var agent = createAgentDelegate(sp, keyString) ?? throw new InvalidOperationException($"The agent factory did not return a valid {nameof(AIAgent)} instance for key '{keyString}'.");
            if (!string.Equals(agent.Name, keyString, StringComparison.Ordinal))
            {
                throw new InvalidOperationException($"The agent factory returned an agent with name '{agent.Name}', but the expected name is '{keyString}'.");
            }

            return agent;
        });

        // Register the agent by name for discovery.
        var agentHostBuilder = GetAgentRegistry(builder);
        agentHostBuilder.AgentNames.Add(name);

        return new HostedAgentBuilder(name, builder);
    }

    private static LocalAgentRegistry GetAgentRegistry(IHostApplicationBuilder builder)
    {
        var descriptor = builder.Services.FirstOrDefault(s => !s.IsKeyedService && s.ServiceType.Equals(typeof(LocalAgentRegistry)));
        if (descriptor?.ImplementationInstance is not LocalAgentRegistry instance)
        {
            instance = new LocalAgentRegistry();
            ConfigureHostBuilder(builder, instance);
        }

        return instance;
    }

    private static void ConfigureHostBuilder(IHostApplicationBuilder builder, LocalAgentRegistry agentHostBuilderContext)
    {
        builder.Services.Add(ServiceDescriptor.Singleton(agentHostBuilderContext));
        builder.Services.AddSingleton<AgentCatalog, LocalAgentCatalog>();
    }
}
