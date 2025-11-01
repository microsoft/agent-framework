// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.OpenAI;
using Microsoft.Agents.AI.Hosting.OpenAI.Conversations;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.AspNetCore.Http.Json;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>
/// Extension methods for <see cref="IServiceCollection"/> to configure OpenAI Responses support.
/// </summary>
public static class MicrosoftAgentAIHostingOpenAIServiceCollectionExtensions
{
    /// <summary>
    /// Adds support for exposing <see cref="AIAgent"/> instances via OpenAI Responses.
    /// Uses the in-memory responses service implementation by default.
    /// </summary>
    /// <param name="services">The <see cref="IServiceCollection"/> to configure.</param>
    /// <param name="configureOptions">Optional action to configure <see cref="InMemoryStorageOptions"/>.</param>
    /// <returns>The <see cref="IServiceCollection"/> for method chaining.</returns>
    public static IServiceCollection AddOpenAIResponses(this IServiceCollection services, Action<InMemoryStorageOptions>? configureOptions = null)
    {
        ArgumentNullException.ThrowIfNull(services);

        services.Configure<JsonOptions>(options
            => options.SerializerOptions.TypeInfoResolverChain.Add(
                OpenAIHostingJsonContext.Default.Options.TypeInfoResolver!));

        // Register storage options
        var storageOptions = new InMemoryStorageOptions();
        configureOptions?.Invoke(storageOptions);
        services.TryAddSingleton(storageOptions);

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
}
