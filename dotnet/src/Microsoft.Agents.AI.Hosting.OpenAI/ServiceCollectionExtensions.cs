// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure OpenAI support.
/// </summary>
public static class MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI ChatCompletions.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddOpenAIChatCompletions(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options => options.SerializerOptions.TypeInfoResolverChain.Add(ChatCompletionsJsonSerializerOptions.Default.TypeInfoResolver!));

        return services;
    }

    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI Responses.
    /// Uses the in-memory responses service implementation.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddOpenAIResponses(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options
            => options.SerializerOptions.TypeInfoResolverChain.Add(
                OpenAIHostingJsonContext.Default.Options.TypeInfoResolver!));

        services.TryAddSingleton<IConversationStorage, InMemoryConversationStorage>();
        services.TryAddSingleton<IAgentConversationIndex, InMemoryAgentConversationIndex>();
        services.TryAddSingleton<InMemoryStorageOptions>();
        services.TryAddSingleton<IResponsesService>(sp =>
        {
            var executor = sp.GetRequiredService<IResponseExecutor>();
            var options = sp.GetRequiredService<InMemoryStorageOptions>();
            var conversationStorage = sp.GetService<IConversationStorage>();
            return new InMemoryResponsesService(executor, options, conversationStorage);
        });
        services.TryAddSingleton<IResponseExecutor, HostedAgentResponseExecutor>();

        return services;
    }

    /// <summary>
    /// Adds in-memory conversation storage and indexing services to the service collection.
    /// This is suitable only for development and testing scenarios.
    /// </summary>
    /// <param name="services">The service collection to add services to.</param>
    /// <returns>The service collection for chaining.</returns>
    public static IServiceCollection AddOpenAIConversations(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);

        // Register storage options
        services.TryAddSingleton<InMemoryStorageOptions>();
        services.TryAddSingleton<IConversationStorage, InMemoryConversationStorage>();
        services.TryAddSingleton<IAgentConversationIndex, InMemoryAgentConversationIndex>();
        return services;
    }
}
